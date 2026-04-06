import hashlib
import json
import logging
import re
import time
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db.models import Prefetch, Count
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

DISEASE_CACHE_KEY     = "rag:diseases:v6"
DISEASE_CACHE_TIMEOUT = 3600
RESULT_CACHE_TIMEOUT  = 300

TFIDF_THRESHOLD = 0.04
MAX_RESULTS = 3


class RAGRetriever:

    def __init__(self):
        self._vectorizer = None
        self._corpus_matrix = None
        self._corpus_hash = None
        self._last_load_time = 0

    # ─────────────────────────────────────────────
    # SAFE DB CHECK
    # ─────────────────────────────────────────────

    def _db_ready(self) -> bool:
        try:
            from django.db import connection
            connection.ensure_connection()
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────
    # STABLE CACHE VERSION
    # ─────────────────────────────────────────────

    def _cache_version(self) -> str:
        from .models import Disease

        try:
            # stable signal: table size only
            count = Disease.objects.count()
            return f"disease:v6:{count}"
        except Exception:
            return "disease:unknown"

    # ─────────────────────────────────────────────
    # LOAD DISEASES (LAZY + RETRY SAFE)
    # ─────────────────────────────────────────────

    def _load_diseases(self) -> List[Dict]:

        cache_key = f"{DISEASE_CACHE_KEY}:{self._cache_version()}"
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        # retry loop (fixes Render cold start issue)
        for attempt in range(5):
            try:
                if not self._db_ready():
                    raise OperationalError("DB not ready")

                from .models import Disease, FirstAidProcedure

                diseases = Disease.objects.only(
                    "id", "name", "description", "common_symptoms"
                ).prefetch_related(
                    Prefetch(
                        "first_aid_procedures",
                        queryset=FirstAidProcedure.objects.only(
                            "steps",
                            "warning_notes",
                            "when_to_seek_help"
                        ),
                        to_attr="_fa"
                    )
                )

                data = []

                for d in diseases:
                    text = " ".join([
                        (d.name or "") * 3,
                        (d.common_symptoms or "") * 2,
                        (d.description or "")
                    ]).lower()

                    fa = d._fa[0] if getattr(d, "_fa", None) else None

                    data.append({
                        "id": d.id,
                        "name": d.name,
                        "search_text": text,
                        "first_aid": {
                            "steps": fa.steps if fa else "",
                            "warning_notes": fa.warning_notes if fa else "",
                            "when_to_seek_help": fa.when_to_seek_help if fa else "",
                        } if fa else None
                    })

                cache.set(cache_key, data, DISEASE_CACHE_TIMEOUT)
                self._last_load_time = time.time()

                logger.info("RAG loaded %d diseases", len(data))
                return data

            except (OperationalError, ProgrammingError):
                logger.warning("RAG DB not ready (attempt %d)", attempt + 1)
                time.sleep(2)

            except Exception as exc:
                logger.error("RAG load error: %s", exc)
                break

        return []

    # ─────────────────────────────────────────────
    # TF-IDF BUILD (SAFE)
    # ─────────────────────────────────────────────

    def _build_vectorizer(self, diseases: List[Dict]):

        corpus = [d["search_text"] for d in diseases]
        combined = "|".join(corpus)

        new_hash = hashlib.md5(combined.encode()).hexdigest()

        if self._vectorizer is None or self._corpus_hash != new_hash:

            try:
                from sklearn.feature_extraction.text import TfidfVectorizer

                self._vectorizer = TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    stop_words="english"
                )

                self._corpus_matrix = self._vectorizer.fit_transform(corpus)
                self._corpus_hash = new_hash

                logger.info("RAG vectorizer rebuilt (%d docs)", len(corpus))

            except Exception as exc:
                logger.error("Vectorizer build failed: %s", exc)
                self._vectorizer = None
                self._corpus_matrix = None

        return self._vectorizer, self._corpus_matrix

    # ─────────────────────────────────────────────
    # TF-IDF RANKING
    # ─────────────────────────────────────────────

    def _tfidf_rank(self, diseases, query):

        if not diseases or self._vectorizer is None:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            vec, matrix = self._build_vectorizer(diseases)
            if vec is None:
                return []

            q_vec = vec.transform([query.lower()])
            scores = cosine_similarity(q_vec, matrix)[0]

            return sorted(
                zip(diseases, scores),
                key=lambda x: x[1],
                reverse=True
            )

        except Exception as exc:
            logger.error("TF-IDF error: %s", exc)
            return []

    # ─────────────────────────────────────────────
    # KEYWORD FALLBACK
    # ─────────────────────────────────────────────

    def _keyword_score(self, disease, symptoms):
        text = disease["search_text"]
        hits = sum(
            1 for s in symptoms
            if re.search(rf"\b{re.escape(s)}\b", text)
        )
        return hits / len(symptoms) if symptoms else 0

    # ─────────────────────────────────────────────
    # PUBLIC WARMUP
    # ─────────────────────────────────────────────

    def warm_up(self):
        try:
            diseases = self._load_diseases()

            if not diseases:
                logger.warning("RAG warm-up skipped: no diseases yet")
                return

            self._build_vectorizer(diseases)

            logger.info("RAG warm-up complete")

        except Exception as exc:
            logger.warning("RAG warm-up failed: %s", exc)

    # ─────────────────────────────────────────────
    # MAIN RETRIEVAL
    # ─────────────────────────────────────────────

    def retrieve_relevant_first_aid(self, user_input, extracted_symptoms):

        if not extracted_symptoms:
            return []

        symptoms = list({
            s.lower().strip()
            for s in extracted_symptoms
            if s.strip()
        })

        if not symptoms:
            return []

        cache_key = "rag:q:" + hashlib.md5(
            json.dumps(sorted(symptoms) + [user_input[:300]]).encode()
        ).hexdigest()

        cached = cache.get(cache_key)
        if cached:
            return cached

        diseases = self._load_diseases()
        if not diseases:
            return []

        query = " ".join(symptoms) + " " + user_input

        results = []

        # TF-IDF
        for disease, score in self._tfidf_rank(diseases, query):
            if score < TFIDF_THRESHOLD:
                break

            if disease.get("first_aid"):
                results.append({
                    "disease": disease["name"],
                    "confidence": round(float(score), 4),
                    "first_aid": disease["first_aid"]
                })

            if len(results) >= MAX_RESULTS:
                break

        # fallback
        if not results:
            scored = [
                (d, self._keyword_score(d, symptoms))
                for d in diseases
            ]

            scored.sort(key=lambda x: x[1], reverse=True)

            for disease, score in scored:
                if score <= 0:
                    break

                if disease.get("first_aid"):
                    results.append({
                        "disease": disease["name"],
                        "confidence": round(score, 4),
                        "first_aid": disease["first_aid"]
                    })

                if len(results) >= MAX_RESULTS:
                    break

        cache.set(cache_key, results, RESULT_CACHE_TIMEOUT)
        return results


# ─────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────

_instance = None


def get_rag_retriever():
    global _instance
    if _instance is None:
        _instance = RAGRetriever()
        logger.info("RAGRetriever singleton created")
    return _instance
