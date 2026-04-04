# chatbot/views.py
"""
Medical Chatbot API Views — pure JSON responses.

API contract (matches frontend index.html):
  POST /api/chat/       { message, session_id }
  POST /api/hospitals/  { latitude, longitude, session_id, emergency_id? }
  POST /api/feedback/   { session_id, disease, rating, feedback }
  GET  /api/health/     → { status: "ok" }
"""

import json
import logging
from math import atan2, cos, radians, sin, sqrt
from typing import Dict, Optional, Tuple

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    ChatMessage, ChatSession, EmergencyLog,
    FirstAidFeedback, SymptomLog, UserProfile,
)
from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import get_rag_retriever

logger        = logging.getLogger(__name__)
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

def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _get_or_create_profile(request, session_id: str):
    try:
        profile = UserProfile.objects.get(session_id=session_id)
        profile.last_seen = timezone.now()
        profile.save(update_fields=["last_seen"])
        return profile
    except UserProfile.DoesNotExist:
        return UserProfile.objects.create(
            session_id=session_id,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )


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
    """Build the markdown string consumed by renderMarkdown() in the frontend."""
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
    """Used by render.yaml healthCheckPath: /api/health/"""
    return JsonResponse({"status": "ok"})


# ── Chat ──────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def process_message(request):
    """
    Process a user symptom message through NLP → emergency detection → RAG.

    Request:  { "message": str, "session_id": str }

    Normal:    { type:"normal", message, symptoms_detected, session_id }
    Emergency: { type:"emergency", severity, message, emergencies,
                 action:"request_location", emergency_id, session_id }
    Error:     { type:"error", message }  — HTTP 4xx / 5xx
    """
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"type": "error", "message": "Invalid JSON body."}, status=400)

    user_message = body.get("message", "").strip()
    session_id   = body.get("session_id", "").strip()

    if not user_message:
        return JsonResponse({"type": "error", "message": "Message cannot be empty."}, status=400)
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {"type": "error", "message": f"Message too long (max {MAX_MESSAGE_LENGTH} chars)."},
            status=400,
        )
    if not session_id:
        return JsonResponse({"type": "error", "message": "session_id is required."}, status=400)

    if not _rate_limit_ok(session_id):
        return JsonResponse({"type": "error", "message": "Too many requests — please wait."}, status=429)

    try:
        profile = _get_or_create_profile(request, session_id)

        with transaction.atomic():
            session, _ = ChatSession.objects.get_or_create(
                session_id=session_id, defaults={"user_profile": profile}
            )
            if not session.user_profile:
                session.user_profile = profile
                session.save(update_fields=["user_profile"])
            user_msg = ChatMessage.objects.create(
                session=session, user_profile=profile,
                role="user", content=user_message,
            )

        # NLP
        try:
            symptoms = nlp_processor.extract_symptoms(user_message)
        except Exception as exc:
            logger.error("extract_symptoms: %s", exc, exc_info=True)
            symptoms = []

        # Emergency detection
        try:
            emergencies = nlp_processor.detect_emergency(user_message)
        except Exception as exc:
            logger.error("detect_emergency: %s", exc, exc_info=True)
            emergencies = []

        if emergencies:
            emergencies.sort(key=lambda x: SEVERITY_LEVELS.get(x["severity"], 0), reverse=True)
            eid = None
            try:
                elog = EmergencyLog.objects.create(
                    user_profile=profile,
                    emergency_keywords=[e["keyword"] for e in emergencies],
                    severity=emergencies[0]["severity"],
                    raw_input=user_message,
                )
                eid = elog.id
            except Exception as exc:
                logger.error("EmergencyLog create: %s", exc)

            try:
                user_msg.emergency_detected = True
                user_msg.save(update_fields=["emergency_detected"])
            except Exception:
                pass

            return JsonResponse({
                "type":         "emergency",
                "severity":     emergencies[0]["severity"],
                "message":      emergencies[0]["message"],
                "emergencies":  emergencies,
                "action":       "request_location",
                "emergency_id": eid,
                "session_id":   session_id,
            })

        # RAG retrieval
        results, matched = [], []
        if symptoms:
            try:
                results = get_rag_retriever().retrieve_relevant_first_aid(user_message, symptoms)
                matched = [{"name": r["disease"], "confidence": r["confidence"]} for r in results]
            except Exception as exc:
                logger.error("RAG retrieve: %s", exc, exc_info=True)

            try:
                SymptomLog.objects.create(
                    user_profile=profile,
                    symptoms=symptoms,
                    raw_input=user_message,
                    matched_diseases=matched,
                )
            except Exception as exc:
                logger.error("SymptomLog create: %s", exc)

        # Build response text
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

        try:
            ChatMessage.objects.create(
                session=session, user_profile=profile,
                role="bot", content=response_text,
            )
        except Exception as exc:
            logger.error("Bot ChatMessage save: %s", exc)

        return JsonResponse({
            "type":              "normal",
            "message":           response_text,
            "symptoms_detected": symptoms,
            "session_id":        session_id,
        })

    except ValidationError as exc:
        return JsonResponse({"type": "error", "message": str(exc)}, status=400)
    except Exception as exc:
        logger.error("process_message unhandled: %s", exc, exc_info=True)
        return JsonResponse({"type": "error", "message": "Server error — please try again."}, status=500)


# ── Hospitals ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def get_nearby_hospitals(request):
    """
    Query OpenStreetMap Overpass API for nearby hospitals / clinics.

    Request:  { "latitude": float, "longitude": float,
                "session_id": str, "emergency_id": int? }
    Response: { "hospitals": [...], "user_location": {lat, lng} }
    """
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    lat          = body.get("latitude")
    lng          = body.get("longitude")
    session_id   = body.get("session_id", "").strip()
    emergency_id = body.get("emergency_id")

    if lat is None or lng is None:
        return JsonResponse({"error": "latitude and longitude are required."}, status=400)
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Coordinates must be numeric."}, status=400)
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return JsonResponse({"error": "Coordinates out of valid range."}, status=400)

    # Update emergency log with shared location
    if emergency_id:
        try:
            elog = EmergencyLog.objects.get(id=int(emergency_id))
            elog.location_shared = True
            elog.latitude        = lat
            elog.longitude       = lng
            elog.save(update_fields=["location_shared", "latitude", "longitude"])
        except (EmergencyLog.DoesNotExist, ValueError):
            pass

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
            # node → lat/lon directly; way → center dict
            el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
            el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if el_lat is None or el_lon is None:
                continue
            name = (
                tags.get("name") or
                tags.get("name:en") or
                tags.get("operator") or
                "Medical Facility"
            )
            addr_parts = list(filter(None, [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city") or tags.get("addr:town"),
            ]))
            address = ", ".join(addr_parts) or "Address unavailable"
            hospitals.append({
                "name":     name,
                "lat":      el_lat,
                "lon":      el_lon,
                "address":  address,
                "phone":    tags.get("phone") or tags.get("contact:phone") or "",
                "distance": _haversine(lat, lng, el_lat, el_lon),
            })
        except (KeyError, TypeError):
            continue

    # Deduplicate by name + approximate coords, then sort by distance
    seen: set = set()
    unique = []
    for h in sorted(hospitals, key=lambda x: x["distance"]):
        key = (h["name"].lower(), round(h["lat"], 3), round(h["lon"], 3))
        if key not in seen:
            seen.add(key)
            unique.append(h)

    unique = unique[:HOSPITAL_LIMIT]

    if emergency_id and unique:
        try:
            elog = EmergencyLog.objects.get(id=int(emergency_id))
            elog.nearby_hospitals_shown = len(unique)
            elog.save(update_fields=["nearby_hospitals_shown"])
        except (EmergencyLog.DoesNotExist, ValueError):
            pass

    return JsonResponse({
        "hospitals":     unique,
        "user_location": {"lat": lat, "lng": lng},
    })


# ── Feedback ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def submit_feedback(request):
    """
    Record user star rating + optional comment.

    Request:  { "session_id": str, "disease": str,
                "rating": int (1-5), "feedback": str }
    Response: { "status": "success", "feedback_id": int }
    """
    if request.method == "OPTIONS":
        return JsonResponse({}, status=200)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    session_id    = body.get("session_id", "").strip()
    disease_name  = body.get("disease", "").strip()[:200]
    rating        = body.get("rating")
    feedback_text = body.get("feedback", "").strip()[:5000]

    if not session_id:
        return JsonResponse({"error": "session_id is required."}, status=400)
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return JsonResponse({"error": "rating must be an integer between 1 and 5."}, status=400)

    # Create profile if this is the first request from this session
    try:
        profile = UserProfile.objects.get(session_id=session_id)
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(session_id=session_id)

    symptom_log = (
        SymptomLog.objects
        .filter(user_profile=profile)
        .order_by("-timestamp")
        .first()
    )

    try:
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
        logger.error("FirstAidFeedback create: %s", exc, exc_info=True)
        return JsonResponse({"error": "Server error saving feedback."}, status=500)
