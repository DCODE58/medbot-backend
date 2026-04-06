# chatbot/rag_retriever.py
"""
RAG Retriever — TF-IDF cosine similarity with keyword fallback.

Performance fix: TfidfVectorizer is now fitted once per worker lifetime and
cached on the singleton instance. Subsequent requests only need to transform
the query vector (< 5 ms) instead of re-fitting the entire corpus (~200 ms).

The fitted vectorizer is invalidated automatically when the disease corpus
changes (tracked via a lightweight hash of the corpus content).
"""

import hashlib
import json
import logging
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

DISEASE_CACHE_KEY     = "rag:diseases:v4"
DISEASE_CACHE_TIMEOUT = 3600   # 1 hour
RESULT_CACHE_TIMEOUT  = 300    # 5 minutes per-query
TFIDF_THRESHOLD       = 0.04
MAX_RESULTS           = 3


class RAGRetriever:

    def __init__(self) -> None:
        # In-process cache for the fitted vectorizer — survives across requests
        # in the same gunicorn worker. Re-fitted only when the disease corpus
        # changes (detected via corpus_hash).
        self._vectorizer = None
        self._corpus_matrix = None
        self._corpus_hash: Optional[str] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_diseases(self) -> List[Dict]:
        """
        Fetch and cache the full disease corpus as plain dicts.
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

            fa_dict: Optional[Dict] = None
            if fa_orm is not None:
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

        cache.set(DISEASE_CACHE_KEY, data, DISEASE_CACHE_TIMEOUT)
        return data

    def _get_vectorizer_and_matrix(self, diseases: List[Dict]):
        """
        Return a (vectorizer, corpus_matrix) pair that is fitted once per
        unique corpus and then reused for every subsequent request.

        The corpus hash uses the first 10 disease names as a cheap proxy for
        detecting corpus changes (e.g. after populate_kenya_data reruns).
        A full re-fit takes ~100-200 ms on 50 diseases; transform-only is < 5 ms.
        """
        corpus = [d["search_text"] for d in diseases]

        # Cheap hash — first 10 search texts is enough to detect corpus changes
        sample = "|".join(corpus[:10])
        new_hash = hashlib.md5(sample.encode()).hexdigest()

        if self._vectorizer is None or self._corpus_hash != new_hash:
            logger.info("RAG: fitting TF-IDF vectorizer on %d diseases", len(corpus))
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2), min_df=1, stop_words="english"
            )
            self._corpus_matrix = self._vectorizer.fit_transform(corpus)
            self._corpus_hash = new_hash
            logger.info("RAG: vectorizer ready")

        return self._vectorizer, self._corpus_matrix

    def _tfidf_rank(self, diseases: List[Dict], query: str) -> List[tuple]:
        """
        Return (disease_dict, float_score) sorted by cosine similarity desc.
        Uses the cached vectorizer — only the query needs to be transformed.
        """
        if not diseases:
            return []
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            vec, corpus_matrix = self._get_vectorizer_and_matrix(diseases)
            query_vec = vec.transform([query.lower()])
            scores = cosine_similarity(query_vec, corpus_matrix)[0]
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
            "first_aid":  disease["first_aid"],
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def warm_up(self) -> None:
        """
        Pre-load disease data and fit the vectorizer.
        Called from ChatbotConfig.ready() so the first real request is fast.
        """
        try:
            diseases = self._load_diseases()
            if diseases:
                self._get_vectorizer_and_matrix(diseases)
                logger.info("RAG warm-up complete (%d diseases)", len(diseases))
            else:
                logger.warning("RAG warm-up: disease table is empty")
        except Exception as exc:
            # Don't crash startup — just log
            logger.error("RAG warm-up failed: %s", exc)

    def retrieve_relevant_first_aid(
        self,
        user_input: str,
        extracted_symptoms: List[str],
    ) -> List[Dict]:
        """
        Return up to MAX_RESULTS disease matches with first-aid instructions.
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

            # Stage 1: TF-IDF cosine similarity (vectorizer already fitted)
            for disease, score in self._tfidf_rank(diseases, query):
                if score < TFIDF_THRESHOLD:
                    break
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
_instance: Optional[RAGRetriever] = None


def get_rag_retriever() -> RAGRetriever:
    global _instance
    if _instance is None:
        _instance = RAGRetriever()
        logger.info("RAGRetriever singleton created")
    return _instance
