"""
rag_retriever.py — Fixed symptom-to-disease matching.

Key fixes vs original:
  1. Direct M2M lookup: uses the Symptom→Disease many-to-many relationship
     populated by populate_kenya_data, so "fever + headache + chills" will
     directly pull diseases that have those Symptom objects linked.
  2. Common-symptoms text scoring: tokenises Disease.common_symptoms and
     counts exact matches against extracted symptom canonical names AND
     the original user text, resolving the key-mismatch bug where NLP
     returned "stomach_ache" but the disease stored "abdominal pain".
  3. TF-IDF is retained as a tertiary signal but the threshold is lowered
     from 0.04 → 0.01 so it contributes on smaller corpora.
  4. Composite scoring: M2M hits + symptom-text hits + TF-IDF, normalised
     to produce a ranked list with meaningful confidence values.
  5. All DB calls cached; graceful fallback to empty list on any error.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db.models import Prefetch
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

DISEASE_CACHE_KEY     = "rag:diseases:v8"
DISEASE_CACHE_TIMEOUT = 3600
RESULT_CACHE_TIMEOUT  = 300
MAX_RESULTS           = 3
TFIDF_THRESHOLD       = 0.01   # lowered from 0.04


# ── Symptom key → canonical text mapping ─────────────────────────────────────
# NLP returns keys like "stomach_ache", "difficulty_breathing".
# Disease.common_symptoms stores human-readable text like "abdominal pain",
# "difficulty breathing".  This dict normalises the mapping.
SYMPTOM_KEY_TO_TEXT: Dict[str, List[str]] = {
    "fever":                ["fever", "high temperature", "chills", "sweating"],
    "headache":             ["headache", "head pain", "migraine"],
    "cough":                ["cough", "coughing"],
    "fatigue":              ["fatigue", "tiredness", "weakness", "exhaustion"],
    "vomiting":             ["vomiting", "nausea"],
    "diarrhea":             ["diarrhea", "diarrhoea", "loose stools"],
    "chest_pain":           ["chest pain", "chest discomfort"],
    "difficulty_breathing": ["difficulty breathing", "shortness of breath",
                             "breathless", "wheezing"],
    "joint_pain":           ["joint pain", "joint ache"],
    "muscle_pain":          ["muscle pain", "body aches", "myalgia"],
    "stomach_ache":         ["abdominal pain", "stomach ache", "stomach pain",
                             "belly pain", "stomach cramps"],
    "rash":                 ["rash", "skin rash"],
    "dehydration":          ["dehydration", "dry mouth"],
    "confusion":            ["confusion", "disoriented", "delirium"],
    "sore_throat":          ["sore throat", "throat pain"],
    "dizziness":            ["dizziness", "lightheaded", "vertigo"],
    "numbness":             ["numbness", "tingling"],
    "swelling":             ["swelling", "swollen", "edema"],
    "weight_loss":          ["weight loss", "losing weight"],
    "night_sweats":         ["night sweats", "sweating at night"],
    "jaundice":             ["jaundice", "yellow eyes", "yellow skin"],
    "blood_cough":          ["coughing blood", "blood in sputum"],
    "frequent_urination":   ["frequent urination"],
    "burning_urination":    ["burning urination", "painful urination"],
    "stiff_neck":           ["stiff neck", "neck stiffness"],
    "convulsions":          ["convulsions", "seizure", "fits"],
    "pale_skin":            ["pale skin", "pallor"],
    "itching":              ["itching"],
    "discharge":            ["discharge"],
    "eye_pain":             ["eye pain", "red eyes"],
    "ear_pain":             ["ear pain"],
}


def _canonical_texts(symptom_keys: List[str]) -> List[str]:
    """
    Convert a list of NLP symptom keys into a flat deduplicated list of
    canonical text phrases that will match against Disease.common_symptoms.
    """
    out: List[str] = []
    seen: set = set()
    for key in symptom_keys:
        texts = SYMPTOM_KEY_TO_TEXT.get(key, [key.replace("_", " ")])
        for t in texts:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


class RAGRetriever:

    def __init__(self):
        self._vectorizer    = None
        self._corpus_matrix = None
        self._corpus_hash   = None
        self._last_load     = 0

    # ── DB readiness ──────────────────────────────────────────────────────────

    def _db_ready(self) -> bool:
        try:
            from django.db import connection
            connection.ensure_connection()
            return True
        except Exception:
            return False

    # ── Disease loader ────────────────────────────────────────────────────────

    def _load_diseases(self) -> List[Dict]:
        """
        Load all diseases with their linked Symptom objects and FirstAidProcedures.
        Each entry includes:
          - id, name, search_text (for TF-IDF)
          - symptom_names: list of canonical symptom names from M2M
          - symptom_texts: flat list of all name + alternative_names variations
          - common_symptoms_text: raw Disease.common_symptoms string
          - first_aid: dict or None
        """
        try:
            count = __import__('chatbot.models', fromlist=['Disease']).Disease.objects.count()
        except Exception:
            count = 0
        cache_key = f"{DISEASE_CACHE_KEY}:{count}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        for attempt in range(5):
            try:
                if not self._db_ready():
                    raise OperationalError("DB not ready")

                from chatbot.models import Disease, FirstAidProcedure, Symptom

                diseases = Disease.objects.prefetch_related(
                    Prefetch(
                        "first_aid_procedures",
                        queryset=FirstAidProcedure.objects.only(
                            "steps", "warning_notes", "when_to_seek_help"
                        ),
                        to_attr="_fa",
                    ),
                    Prefetch(
                        "symptoms",
                        queryset=Symptom.objects.only("name", "alternative_names"),
                        to_attr="_symptoms",
                    ),
                )

                data: List[Dict] = []
                for d in diseases:
                    fa = d._fa[0] if getattr(d, "_fa", None) else None

                    # All symptom text variations from linked Symptom objects
                    sym_names: List[str] = []
                    sym_texts: List[str] = []
                    for s in getattr(d, "_symptoms", []):
                        sym_names.append(s.name.lower())
                        sym_texts.append(s.name.lower())
                        for alt in s.alternative_names.split(","):
                            t = alt.strip().lower()
                            if t:
                                sym_texts.append(t)

                    common_lower = (d.common_symptoms or "").lower()

                    # Build TF-IDF corpus text
                    search_text = " ".join([
                        (d.name or "") * 3,
                        (d.common_symptoms or "") * 2,
                        (d.description or ""),
                        " ".join(sym_names),
                    ]).lower()

                    data.append({
                        "id":                   d.id,
                        "name":                 d.name,
                        "search_text":          search_text,
                        "symptom_names":        sym_names,
                        "symptom_texts":        sym_texts,
                        "common_symptoms_text": common_lower,
                        "first_aid": {
                            "steps":             fa.steps if fa else "",
                            "warning_notes":     fa.warning_notes if fa else "",
                            "when_to_seek_help": fa.when_to_seek_help if fa else "",
                        } if fa else None,
                    })

                cache.set(cache_key, data, DISEASE_CACHE_TIMEOUT)
                self._last_load = time.time()
                logger.info("RAG loaded %d diseases", len(data))
                return data

            except (OperationalError, ProgrammingError):
                logger.warning("RAG DB not ready (attempt %d)", attempt + 1)
                time.sleep(2)
            except Exception as exc:
                logger.error("RAG load error: %s", exc)
                break

        return []

    # ── TF-IDF ────────────────────────────────────────────────────────────────

    def _build_vectorizer(self, diseases: List[Dict]):
        corpus   = [d["search_text"] for d in diseases]
        combined = "|".join(corpus)
        new_hash = hashlib.md5(combined.encode()).hexdigest()

        if self._vectorizer is None or self._corpus_hash != new_hash:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer

                self._vectorizer = TfidfVectorizer(
                    ngram_range=(1, 3),
                    min_df=1,
                    stop_words="english",
                )
                self._corpus_matrix = self._vectorizer.fit_transform(corpus)
                self._corpus_hash   = new_hash
                logger.info("RAG vectorizer rebuilt (%d docs)", len(corpus))
            except Exception as exc:
                logger.error("Vectorizer build failed: %s", exc)
                self._vectorizer    = None
                self._corpus_matrix = None

        return self._vectorizer, self._corpus_matrix

    def _tfidf_scores(self, diseases: List[Dict], query: str) -> Dict[int, float]:
        if not diseases or not query:
            return {}
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            vec, matrix = self._build_vectorizer(diseases)
            if vec is None:
                return {}

            q_vec  = vec.transform([query.lower()])
            scores = cosine_similarity(q_vec, matrix)[0]
            return {d["id"]: float(s) for d, s in zip(diseases, scores)}
        except Exception as exc:
            logger.error("TF-IDF error: %s", exc)
            return {}

    # ── Symptom matching ──────────────────────────────────────────────────────

    def _m2m_score(self, disease: Dict, canonical_texts: List[str]) -> float:
        """
        Fraction of requested canonical symptom texts that appear in the
        disease's linked Symptom objects (name + alternatives).
        """
        if not canonical_texts:
            return 0.0
        sym_set = set(disease["symptom_texts"])
        hits = sum(1 for t in canonical_texts if t in sym_set)
        return hits / len(canonical_texts)

    def _common_symptoms_score(self, disease: Dict, canonical_texts: List[str]) -> float:
        """
        Fraction of canonical symptom texts that appear in
        Disease.common_symptoms (the raw comma-separated text field).
        Uses partial substring matching for robustness.
        """
        if not canonical_texts:
            return 0.0
        cs = disease["common_symptoms_text"]
        hits = sum(1 for t in canonical_texts if t in cs)
        return hits / len(canonical_texts)

    def _user_text_score(self, disease: Dict, user_input: str) -> float:
        """
        Check how many of the disease's linked symptom variations appear
        directly in the user's raw input.
        """
        if not user_input:
            return 0.0
        text   = user_input.lower()
        sym_set = set(disease["symptom_texts"])
        if not sym_set:
            return 0.0
        hits = sum(1 for t in sym_set if len(t) > 3 and t in text)
        return min(hits / max(len(sym_set), 1), 1.0)

    # ── Warmup ────────────────────────────────────────────────────────────────

    def warm_up(self):
        try:
            diseases = self._load_diseases()
            if not diseases:
                logger.warning("RAG warm-up skipped: no diseases yet")
                return
            self._build_vectorizer(diseases)
            logger.info("RAG warm-up complete (%d diseases)", len(diseases))
        except Exception as exc:
            logger.warning("RAG warm-up failed: %s", exc)

    # ── Main retrieval ────────────────────────────────────────────────────────

    def retrieve_relevant_first_aid(
        self,
        user_input: str,
        extracted_symptoms: List[str],
    ) -> List[Dict]:
        """
        Match symptoms to diseases and return ranked first-aid results.

        Scoring pipeline (all weights normalised to 0–1):
          composite = 0.40 * m2m_score
                    + 0.35 * common_symptoms_score
                    + 0.15 * tfidf_score
                    + 0.10 * user_text_score

        Only diseases with a first-aid procedure are returned.
        """
        if not extracted_symptoms:
            return []

        symptoms = list({s.lower().strip() for s in extracted_symptoms if s.strip()})
        if not symptoms:
            return []

        cache_key = "rag:q2:" + hashlib.md5(
            json.dumps(sorted(symptoms) + [user_input[:200]]).encode()
        ).hexdigest()

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        diseases = self._load_diseases()
        if not diseases:
            return []

        # Canonical text phrases for the extracted symptom keys
        canon_texts = _canonical_texts(symptoms)
        query       = " ".join(canon_texts) + " " + user_input

        # TF-IDF scores (keyed by disease id)
        tfidf_map = self._tfidf_scores(diseases, query)

        # Composite scoring
        scored: List[tuple] = []
        for d in diseases:
            m2m    = self._m2m_score(d, canon_texts)
            csym   = self._common_symptoms_score(d, canon_texts)
            tfidf  = min(tfidf_map.get(d["id"], 0.0) / max(TFIDF_THRESHOLD, 0.001), 1.0)
            utext  = self._user_text_score(d, user_input)

            composite = (0.40 * m2m) + (0.35 * csym) + (0.15 * tfidf) + (0.10 * utext)
            if composite > 0:
                scored.append((d, composite))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict] = []
        for disease, score in scored:
            if not disease.get("first_aid"):
                continue
            results.append({
                "disease":    disease["name"],
                "confidence": round(score, 4),
                "first_aid":  disease["first_aid"],
            })
            if len(results) >= MAX_RESULTS:
                break

        # Last-resort: if nothing scored > 0 but we still have symptoms,
        # return the top TF-IDF match (any score) with a low-confidence flag
        if not results and tfidf_map:
            best_id    = max(tfidf_map, key=tfidf_map.get)
            best_score = tfidf_map[best_id]
            if best_score > 0:
                for d in diseases:
                    if d["id"] == best_id and d.get("first_aid"):
                        results.append({
                            "disease":    d["name"],
                            "confidence": round(best_score * 0.3, 4),
                            "first_aid":  d["first_aid"],
                        })
                        break

        cache.set(cache_key, results, RESULT_CACHE_TIMEOUT)
        logger.info(
            "RAG matched %d result(s) for symptoms=%s",
            len(results), symptoms
        )
        return results


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[RAGRetriever] = None


def get_rag_retriever() -> RAGRetriever:
    global _instance
    if _instance is None:
        _instance = RAGRetriever()
        logger.info("RAGRetriever singleton created")
    return _instance
