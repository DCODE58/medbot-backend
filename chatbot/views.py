# chatbot/views.py
"""
Medical Chatbot API Views — pure JSON responses.

Architecture change vs original:
  The original view did DB writes (UserProfile, ChatSession, ChatMessage)
  BEFORE NLP and RAG.  Any DB hiccup (stale connection, cold-start latency,
  missing table) therefore killed the entire response with 500.

  New order inside process_message:
    1. Parse + validate input          (no DB)
    2. Rate-limit check                (in-memory cache only)
    3. NLP symptom extraction          (no DB — hardcoded dict + cached ORM)
    4. Emergency detection             (cached ORM, falls back to empty list)
    5. RAG retrieval                   (cached ORM, falls back gracefully)
    6. Build response text             (no DB)
    7. Persist to DB (non-blocking)    (each write in its own try/except)
    8. Return JsonResponse

  This means the chat ALWAYS responds even when the database is temporarily
  unreachable, restarting, or waking from sleep (Render free-tier behaviour).
"""

import json
import logging
from math import atan2, cos, radians, sin, sqrt
from typing import Dict, Optional

import requests
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import get_rag_retriever

logger = logging.getLogger(__name__)

nlp_processor = MedicalNLPProcessor()

# ── Constants ─────────────────────────────────────────────────────────────────
SEVERITY_LEVELS       = {"CRITICAL": 3, "URGENT": 2, "CAUTION": 1}
MAX_MESSAGE_LENGTH    = 5000
CONFIDENCE_LOW        = 0.5
RATE_LIMIT_SECONDS    = 1
HOSPITAL_LIMIT        = 10
HOSPITAL_RADIUS_M     = 5000
HAVERSINE_RADIUS_KM   = 6371
OVERPASS_TIMEOUT_S    = 12
API_REQUEST_TIMEOUT_S = 12


# ── Utilities ─────────────────────────────────────────────────────────────────

def _client_ip(request) -> Optional[str]:
    """Return client IP, or None if unavailable/unparseable."""
    try:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip  = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
        return ip if ip else None
    except Exception:
        return None


def _get_or_create_profile(request, session_id: str):
    """
    Fetch or create a UserProfile for this session.
    Uses get_or_create (atomic) to avoid race conditions.
    Returns None on any DB error so callers can degrade gracefully.
    """
    from .models import UserProfile
    try:
        profile, created = UserProfile.objects.get_or_create(
            session_id=session_id,
            defaults={
                "ip_address": _client_ip(request),
                "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:500],
            },
        )
        if not created:
            # fire-and-forget last_seen update — don't block on it
            UserProfile.objects.filter(pk=profile.pk).update(last_seen=timezone.now())
        return profile
    except Exception as exc:
        logger.warning("UserProfile get_or_create failed: %s", exc)
        return None


def _haversine(lat1, lon1, lat2, lon2) -> float:
    if lat2 is None or lon2 is None:
        return 999_999.0
    try:
        r1, o1, r2, o2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        a = sin((r2 - r1) / 2) ** 2 + cos(r1) * cos(r2) * sin((o2 - o1) / 2) ** 2
        return round(HAVERSINE_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1 - a)), 2)
    except (TypeError, ValueError):
        return 999_999.0


def _format_response(disease: str, first_aid: Dict, confidence: float) -> str:
    lines = [
        f"**Based on your symptoms, you may have {disease}**\n",
        "**First Aid Steps:**",
        (first_aid.get("steps") or "No steps available.") + "\n",
    ]
    if first_aid.get("warning_notes"):
        lines.append(f"**⚠️ WARNING:** {first_aid['warning_notes']}\n")
    lines.append("**When to Seek Help:**")
    lines.append(first_aid.get("when_to_seek_help") or "Consult a healthcare provider.")
    if confidence < CONFIDENCE_LOW:
        lines.append(
            "\n*Note: Low-confidence match — please describe your symptoms in more detail "
            "or consult a healthcare provider.*"
        )
    return "\n".join(lines)


def _rate_limit_ok(session_id: str) -> bool:
    key = f"rl:{session_id}"
    if cache.get(key):
        return False
    cache.set(key, 1, RATE_LIMIT_SECONDS)
    return True


# ── Health check ──────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def health_check(request):
    return JsonResponse({"status": "ok"})


# ── Chat ──────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def process_message(request):
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    # ── 1. Parse input ────────────────────────────────────────────────────────
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"type": "error", "message": "Invalid JSON body."}, status=400)

    user_message = (body.get("message") or "").strip()
    session_id   = (body.get("session_id") or "").strip()

    if not user_message:
        return JsonResponse({"type": "error", "message": "Message cannot be empty."}, status=400)
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {"type": "error", "message": f"Message too long (max {MAX_MESSAGE_LENGTH} chars)."},
            status=400,
        )
    if not session_id:
        return JsonResponse({"type": "error", "message": "session_id is required."}, status=400)

    # ── 2. Rate limit ─────────────────────────────────────────────────────────
    if not _rate_limit_ok(session_id):
        return JsonResponse({"type": "error", "message": "Too many requests — please wait."}, status=429)

    # ── 3. NLP — symptom extraction (hardcoded dict, no DB required) ──────────
    try:
        symptoms = nlp_processor.extract_symptoms(user_message)
    except Exception as exc:
        logger.error("extract_symptoms failed: %s", exc, exc_info=True)
        symptoms = []

    # ── 4. Emergency detection (uses cached DB, falls back to []) ─────────────
    try:
        emergencies = nlp_processor.detect_emergency(user_message)
    except Exception as exc:
        logger.error("detect_emergency failed: %s", exc, exc_info=True)
        emergencies = []

    # ── 5. Handle emergency path ──────────────────────────────────────────────
    if emergencies:
        emergencies.sort(key=lambda x: SEVERITY_LEVELS.get(x["severity"], 0), reverse=True)

        # Persist emergency log (non-blocking — failure doesn't affect response)
        eid = _save_emergency_log(request, session_id, user_message, emergencies)

        return JsonResponse({
            "type":         "emergency",
            "severity":     emergencies[0]["severity"],
            "message":      emergencies[0]["message"],
            "emergencies":  emergencies,
            "action":       "request_location",
            "emergency_id": eid,
            "session_id":   session_id,
        })

    # ── 6. RAG retrieval (uses cached DB, falls back to []) ───────────────────
    results = []
    if symptoms:
        try:
            results = get_rag_retriever().retrieve_relevant_first_aid(user_message, symptoms)
        except Exception as exc:
            logger.error("RAG retrieve failed: %s", exc, exc_info=True)

    # ── 7. Build response text ────────────────────────────────────────────────
    if results:
        best = results[0]
        response_text = _format_response(best["disease"], best["first_aid"], best["confidence"])
    elif symptoms:
        response_text = (
            f"I identified these symptoms: {', '.join(symptoms)}.\n\n"
            "I couldn't match them to a specific condition in our database. "
            "Please provide more detail or consult a healthcare provider."
        )
    else:
        response_text = (
            "I couldn't identify any symptoms from your message.\n\n"
            "Please describe how you feel — for example: "
            "*'I have fever, headache, and body aches'*."
        )

    # ── 8. Persist to DB (non-blocking) ───────────────────────────────────────
    _save_chat(request, session_id, user_message, response_text, symptoms, results)

    # ── 9. Return ─────────────────────────────────────────────────────────────
    return JsonResponse({
        "type":              "normal",
        "message":           response_text,
        "symptoms_detected": symptoms,
        "session_id":        session_id,
    })


# ── Non-blocking DB helpers ───────────────────────────────────────────────────

def _save_chat(request, session_id, user_message, response_text, symptoms, results):
    """
    Persist UserProfile / ChatSession / ChatMessage / SymptomLog.
    Every operation is individually guarded — a failure in one step
    does NOT prevent subsequent steps or the HTTP response.
    """
    from .models import ChatMessage, ChatSession, SymptomLog

    profile = _get_or_create_profile(request, session_id)

    # ChatSession
    session = None
    try:
        if profile:
            session, _ = ChatSession.objects.get_or_create(
                session_id=session_id,
                defaults={"user_profile": profile},
            )
        else:
            session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    except Exception as exc:
        logger.warning("ChatSession get_or_create failed: %s", exc)

    # User ChatMessage
    if session:
        try:
            ChatMessage.objects.create(
                session=session,
                user_profile=profile,
                role="user",
                content=user_message,
            )
        except Exception as exc:
            logger.warning("User ChatMessage save failed: %s", exc)

        # Bot ChatMessage
        try:
            ChatMessage.objects.create(
                session=session,
                user_profile=profile,
                role="bot",
                content=response_text,
            )
        except Exception as exc:
            logger.warning("Bot ChatMessage save failed: %s", exc)

    # SymptomLog
    if profile and symptoms:
        try:
            matched = [{"name": r["disease"], "confidence": r["confidence"]} for r in results]
            SymptomLog.objects.create(
                user_profile=profile,
                symptoms=symptoms,
                raw_input=user_message,
                matched_diseases=matched,
            )
        except Exception as exc:
            logger.warning("SymptomLog save failed: %s", exc)


def _save_emergency_log(request, session_id, user_message, emergencies) -> Optional[int]:
    """
    Persist an EmergencyLog and return its id (or None on failure).
    """
    from .models import EmergencyLog

    profile = _get_or_create_profile(request, session_id)
    if not profile:
        return None
    try:
        elog = EmergencyLog.objects.create(
            user_profile=profile,
            emergency_keywords=[e["keyword"] for e in emergencies],
            severity=emergencies[0]["severity"],
            raw_input=user_message,
        )
        return elog.id
    except Exception as exc:
        logger.warning("EmergencyLog save failed: %s", exc)
        return None


# ── Hospitals ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def get_nearby_hospitals(request):
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    lat          = body.get("latitude")
    lng          = body.get("longitude")
    session_id   = (body.get("session_id") or "").strip()
    emergency_id = body.get("emergency_id")

    if lat is None or lng is None:
        return JsonResponse({"error": "latitude and longitude are required."}, status=400)
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Coordinates must be numeric."}, status=400)
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return JsonResponse({"error": "Coordinates out of valid range."}, status=400)

    # Update emergency log (non-blocking)
    if emergency_id:
        try:
            from .models import EmergencyLog
            EmergencyLog.objects.filter(id=int(emergency_id)).update(
                location_shared=True, latitude=lat, longitude=lng
            )
        except Exception as exc:
            logger.warning("EmergencyLog location update failed: %s", exc)

    overpass_query = (
        f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];\n"
        f"(\n"
        f'  node["amenity"="hospital"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f'  node["amenity"="clinic"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f'  node["amenity"="health_post"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f'  node["healthcare"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f'  way["amenity"="hospital"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f'  way["amenity"="clinic"](around:{HOSPITAL_RADIUS_M},{lat},{lng});\n'
        f");\n"
        f"out center body;\n"
    )

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": overpass_query},
            timeout=API_REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        osm_data = resp.json()
    except requests.Timeout:
        logger.warning("Overpass timed out for lat=%s lng=%s", lat, lng)
        return JsonResponse({"error": "Hospital search timed out. Please call 999 or 112."}, status=503)
    except requests.RequestException as exc:
        logger.error("Overpass API error: %s", exc)
        return JsonResponse({"error": "Unable to fetch hospital data."}, status=503)

    hospitals = []
    for el in osm_data.get("elements", []):
        try:
            tags   = el.get("tags", {})
            el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
            el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if el_lat is None or el_lon is None:
                continue
            name = (
                tags.get("name") or tags.get("name:en") or
                tags.get("operator") or "Medical Facility"
            )
            addr_parts = list(filter(None, [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city") or tags.get("addr:town"),
            ]))
            hospitals.append({
                "name":     name,
                "lat":      el_lat,
                "lon":      el_lon,
                "address":  ", ".join(addr_parts) or "Address unavailable",
                "phone":    tags.get("phone") or tags.get("contact:phone") or "",
                "distance": _haversine(lat, lng, el_lat, el_lon),
            })
        except (KeyError, TypeError):
            continue

    seen, unique = set(), []
    for h in sorted(hospitals, key=lambda x: x["distance"]):
        key = (h["name"].lower(), round(h["lat"], 3), round(h["lon"], 3))
        if key not in seen:
            seen.add(key)
            unique.append(h)
    unique = unique[:HOSPITAL_LIMIT]

    # Update hospitals_shown count (non-blocking)
    if emergency_id and unique:
        try:
            from .models import EmergencyLog
            EmergencyLog.objects.filter(id=int(emergency_id)).update(
                nearby_hospitals_shown=len(unique)
            )
        except Exception as exc:
            logger.warning("EmergencyLog hospitals_shown update failed: %s", exc)

    return JsonResponse({"hospitals": unique, "user_location": {"lat": lat, "lng": lng}})


# ── Feedback ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def submit_feedback(request):
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    session_id    = (body.get("session_id") or "").strip()
    disease_name  = (body.get("disease") or "")[:200].strip()
    rating        = body.get("rating")
    feedback_text = (body.get("feedback") or "")[:5000].strip()

    if not session_id:
        return JsonResponse({"error": "session_id is required."}, status=400)
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return JsonResponse({"error": "rating must be an integer between 1 and 5."}, status=400)

    try:
        from .models import FirstAidFeedback, SymptomLog, UserProfile

        profile, _ = UserProfile.objects.get_or_create(session_id=session_id)

        symptom_log = (
            SymptomLog.objects
            .filter(user_profile=profile)
            .order_by("-timestamp")
            .first()
        )

        fb = FirstAidFeedback.objects.create(
            user_profile=profile,
            symptom_log=symptom_log,
            disease_name=disease_name,
            response_given="",
            rating=rating,
            feedback_text=feedback_text,
        )
        return JsonResponse({"status": "success", "feedback_id": fb.id})

    except Exception as exc:
        logger.error("submit_feedback failed: %s", exc, exc_info=True)
        return JsonResponse({"error": "Server error saving feedback."}, status=500)
