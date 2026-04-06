# chatbot/rag_retriever.py

import hashlib
import json
import logging
import re
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db.models import Prefetch, Max, Count
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

DISEASE_CACHE_KEY     = "rag:diseases:v5"
DISEASE_CACHE_TIMEOUT = 3600   # 1 hour
RESULT_CACHE_TIMEOUT  = 300    # 5 minutes
TFIDF_THRESHOLD       = 0.04
MAX_RESULTS           = 3


class RAGRetriever:

    def __init__(self) -> None:
        self._vectorizer = None
        self._corpus_matrix = None
        self._corpus_hash: Optional[str] = None

    # ── Cache Versioning ──────────────────────────────────────────────────────

    def _get_cache_version(self) -> str:
        from .models import Disease
        try:
            meta = Disease.objects.aggregate(
                count=Count("id"),
                max_id=Max("id")
            )
            return f"{meta['count']}-{meta['max_id']}"
        except Exception:
            return "unknown"

    # ── Load Diseases ─────────────────────────────────────────────────────────

    def _load_diseases(self) -> List[Dict]:
        cache_key = f"{DISEASE_CACHE_KEY}:{self._get_cache_version()}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from .models import Disease, FirstAidProcedure

            diseases = Disease.objects.only(
                "id", "name", "description", "common_symptoms"
            ).prefetch_related(
                Prefetch(
                    "first_aid_procedures",
                    queryset=FirstAidProcedure.objects.only(
                        "disease_id", "steps", "warning_notes", "when_to_seek_help"
                    ),
                    to_attr="_fa",
                )
            )

            data: List[Dict] = []

            for d in diseases:
                # Weighted text for better ranking
                search_text = " ".join([
                    (d.name or "") * 3,
                    (d.common_symptoms or "") * 2,
                    (d.description or "")
                ]).lower()

                fa_orm = (d._fa[0] if getattr(d, "_fa", None) else None)

                fa_dict: Optional[Dict] = None
                if fa_orm:
                    fa_dict = {
                        "steps":             fa_orm.steps or "",
                        "warning_notes":     fa_orm.warning_notes or "",
                        "when_to_seek_help": fa_orm.when_to_seek_help or "",
                    }

                data.append({
                    "id":          d.id,
                    "name":        d.name,
                    "search_text": search_text,
                    "first_aid":   fa_dict,
                })

            cache.set(cache_key, data, DISEASE_CACHE_TIMEOUT)
            return data

        except (OperationalError, ProgrammingError):
            logger.warning("RAG: DB not ready when loading diseases")
            return []

    # ── Vectorizer ────────────────────────────────────────────────────────────

    def _get_vectorizer_and_matrix(self, diseases: List[Dict]):
        corpus = [d["search_text"] for d in diseases]

        # Strong hash (full corpus)
        combined = "|".join(corpus)
        new_hash = hashlib.md5(combined.encode()).hexdigest()

        if self._vectorizer is None or self._corpus_hash != new_hash:
            logger.info("RAG: fitting TF-IDF vectorizer on %d diseases", len(corpus))

            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                min_df=1,
                stop_words="english"
            )

            self._corpus_matrix = self._vectorizer.fit_transform(corpus)
            self._corpus_hash = new_hash

            logger.info("RAG: vectorizer ready")

        return self._vectorizer, self._corpus_matrix

    # ── Ranking ───────────────────────────────────────────────────────────────

    def _tfidf_rank(self, diseases: List[Dict], query: str) -> List[tuple]:
        if not diseases:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            vec, matrix = self._get_vectorizer_and_matrix(diseases)
            query_vec = vec.transform([query.lower()])
            scores = cosine_similarity(query_vec, matrix)[0]

            return sorted(
                zip(diseases, (float(s) for s in scores)),
                key=lambda x: x[1],
                reverse=True,
            )

        except Exception as exc:
            logger.error("TF-IDF scoring error: %s", exc)
            return []

    def _keyword_score(self, disease: Dict, symptoms: List[str]) -> float:
        text = disease["search_text"]
        hits = sum(
            1 for s in symptoms
            if re.search(rf"\b{re.escape(s)}\b", text)
        )
        return hits / len(symptoms) if symptoms else 0.0

    def _build_result(self, disease: Dict, score: float) -> Optional[Dict]:
        if not disease.get("first_aid"):
            return None

        return {
            "disease":    disease["name"],
            "confidence": round(score, 4),
            "first_aid":  disease["first_aid"],
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def warm_up(self) -> None:
        try:
            diseases = self._load_diseases()
            if diseases:
                self._get_vectorizer_and_matrix(diseases)
                logger.info("RAG warm-up complete (%d diseases)", len(diseases))
            else:
                logger.warning("RAG warm-up skipped: no diseases found")

        except (OperationalError, ProgrammingError):
            logger.warning("RAG warm-up skipped: DB not ready")
        except Exception as exc:
            logger.exception("RAG warm-up failed: %s", exc)

    def retrieve_relevant_first_aid(
        self,
        user_input: str,
        extracted_symptoms: List[str],
    ) -> List[Dict]:

        if not extracted_symptoms:
            return []

        symptoms = list({s.lower().strip() for s in extracted_symptoms if s.strip()})
        if not symptoms:
            return []

        cache_key = "rag:q:" + hashlib.md5(
            json.dumps(sorted(symptoms) + [user_input[:500]]).encode()
        ).hexdigest()

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            diseases = self._load_diseases()
            if not diseases:
                return []

            query = " ".join(symptoms) + " " + user_input
            results: List[Dict] = []

            # TF-IDF stage
            for disease, score in self._tfidf_rank(diseases, query):
                if score < TFIDF_THRESHOLD:
                    break

                r = self._build_result(disease, score)
                if r:
                    results.append(r)

                if len(results) >= MAX_RESULTS:
                    break

            # Fallback
            if not results:
                kw_scored = [
                    (d, self._keyword_score(d, symptoms))
                    for d in diseases
                ]
                kw_scored.sort(key=lambda x: x[1], reverse=True)

                for disease, score in kw_scored:
                    if score <= 0:
                        break

                    r = self._build_result(disease, score)
                    if r:
                        results.append(r)

                    if len(results) >= MAX_RESULTS:
                        break

            cache.set(cache_key, results, RESULT_CACHE_TIMEOUT)
            return results

        except Exception as exc:
            logger.error("RAG retrieval error: %s", exc, exc_info=True)
            return []


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[RAGRetriever] = None


def get_rag_retriever() -> RAGRetriever:
    global _instance
    if _instance is None:
        _instance = RAGRetriever()
        logger.info("RAGRetriever singleton created")
    return _instance
