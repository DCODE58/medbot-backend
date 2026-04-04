# chatbot/rag_retriever.py
"""
RAG Retriever — TF-IDF cosine similarity with keyword fallback.

Fix 5: Replaced `RAGRetriever | None` (Python 3.10+ union syntax) with
        `Optional[RAGRetriever]` so the module loads on Python 3.9 too.

Fix 6: `first_aid` was stored as an ORM object inside the DatabaseCache.
        When the cache row expires and is re-read in a new Django session,
        Django tries to unpickle the ORM instance which triggers an
        OperationalError (DB connection not yet set up for that thread).
        All disease data is now converted to plain dicts before cache.set().
"""

import hashlib
import json
import logging
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

DISEASE_CACHE_KEY     = "rag:diseases:v4"   # bumped — new shape (plain dicts)
DISEASE_CACHE_TIMEOUT = 3600                 # 1 hour
RESULT_CACHE_TIMEOUT  = 300                  # 5 minutes per-query
TFIDF_THRESHOLD       = 0.04
MAX_RESULTS           = 3


class RAGRetriever:

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_diseases(self) -> List[Dict]:
        """
        Fetch and cache the full disease corpus as plain dicts.

        Fix 6: previously stored ORM FirstAidProcedure objects in the cache.
        Unpickling ORM objects from DatabaseCache in a new thread/worker
        raises OperationalError because the DB connection isn't ready yet.
        We now serialise to plain dicts before calling cache.set().

        Returns list of:
          { id, name, search_text,
            first_aid: { steps, warning_notes, when_to_seek_help } | None }
        """
        cached = cache.get(DISEASE_CACHE_KEY)
        if cached is not None:
            return cached

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
            search_text = " ".join(
                filter(None, [d.name or "", d.description or "", d.common_symptoms or ""])
            ).lower()

            fa_orm = (d._fa[0] if getattr(d, "_fa", None) else None)

            # Fix 6: convert ORM object → plain dict so DatabaseCache can safely
            # pickle and unpickle across workers without touching the DB.
            fa_dict: Optional[Dict] = None
            if fa_orm is not None:
                fa_dict = {
                    "steps":              fa_orm.steps or "",
                    "warning_notes":      fa_orm.warning_notes or "",
                    "when_to_seek_help":  fa_orm.when_to_seek_help or "",
                }

            data.append({
                "id":          d.id,
                "name":        d.name,
                "search_text": search_text,
                "first_aid":   fa_dict,   # plain dict or None — safe to pickle
            })

        cache.set(DISEASE_CACHE_KEY, data, DISEASE_CACHE_TIMEOUT)
        return data

    def _tfidf_rank(self, diseases: List[Dict], query: str) -> List[tuple]:
        """Return (disease_dict, float_score) pairs sorted by cosine similarity desc."""
        if not diseases:
            return []
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            corpus = [d["search_text"] for d in diseases]
            vec    = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
            matrix = vec.fit_transform(corpus + [query.lower()])
            scores = cosine_similarity(matrix[-1], matrix[:-1])[0]
            return sorted(
                zip(diseases, (float(s) for s in scores)),
                key=lambda x: x[1],
                reverse=True,
            )
        except Exception as exc:
            logger.error("TF-IDF scoring error: %s", exc)
            return []

    def _keyword_score(self, disease: Dict, symptoms: List[str]) -> float:
        """Fallback: fraction of symptom strings found in the disease search_text."""
        if not symptoms:
            return 0.0
        hits = sum(1 for s in symptoms if s.lower() in disease["search_text"])
        return hits / len(symptoms)

    def _build_result(self, disease: Dict, score: float) -> Optional[Dict]:
        """Return API result dict or None when the disease has no first-aid procedure."""
        if not disease.get("first_aid"):
            return None
        return {
            "disease":    disease["name"],
            "confidence": round(score, 4),
            "first_aid":  disease["first_aid"],   # already a plain dict (Fix 6)
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve_relevant_first_aid(
        self,
        user_input: str,
        extracted_symptoms: List[str],
    ) -> List[Dict]:
        """
        Return up to MAX_RESULTS disease matches with first-aid instructions.

        Args:
            user_input:          Raw text from the user.
            extracted_symptoms:  Symptom strings from MedicalNLPProcessor.

        Returns:
            [{ disease, confidence,
               first_aid: { steps, warning_notes, when_to_seek_help } }, ...]
        """
        if not extracted_symptoms:
            return []

        symptoms = list({s.lower().strip() for s in extracted_symptoms if s.strip()})
        if not symptoms:
            return []

        # Per-query result cache
        cache_key = "rag:q:" + hashlib.md5(
            json.dumps(sorted(symptoms) + [user_input[:500]]).encode()
        ).hexdigest()
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            diseases = self._load_diseases()
            if not diseases:
                logger.warning("RAG: disease table is empty — run populate_kenya_data")
                return []

            query   = " ".join(symptoms) + " " + user_input
            results: List[Dict] = []

            # Stage 1: TF-IDF cosine similarity
            for disease, score in self._tfidf_rank(diseases, query):
                if score < TFIDF_THRESHOLD:
                    break   # sorted descending — nothing below threshold is useful
                r = self._build_result(disease, score)
                if r:
                    results.append(r)
                if len(results) >= MAX_RESULTS:
                    break

            # Stage 2: keyword substring fallback
            if not results:
                logger.debug("TF-IDF returned nothing — falling back to keyword match")
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
            logger.error("RAGRetriever.retrieve_relevant_first_aid: %s", exc, exc_info=True)
            return []


# ── Singleton ─────────────────────────────────────────────────────────────────
# Fix 5: Optional[RAGRetriever] instead of RAGRetriever | None (3.10+ only)
_instance: Optional[RAGRetriever] = None


def get_rag_retriever() -> RAGRetriever:
    global _instance
    if _instance is None:
        _instance = RAGRetriever()
        logger.info("RAGRetriever singleton created")
    return _instance
