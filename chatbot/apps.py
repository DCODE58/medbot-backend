import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "populate_kenya_data", "shell", "dbshell", "check", "test",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "chatbot"

    def ready(self) -> None:
        # Never warm up during management commands -- they don't need it and
        # some (migrate, collectstatic) run before the DB is fully ready.
        if any(cmd in sys.argv for cmd in _SKIP_COMMANDS):
            return

        self._warm_rag()
        self._warm_nlp()

    def _warm_rag(self) -> None:
        """Fit the TF-IDF vectorizer once so the first real request is fast."""
        try:
            from .rag_retriever import get_rag_retriever
            get_rag_retriever().warm_up()
        except Exception as exc:
            # Non-fatal: the first request will warm up instead
            logger.warning("RAG warm-up skipped: %s", exc)

    def _warm_nlp(self) -> None:
        """Prime symptom and emergency keyword caches.
        Imports nlp_processor directly -- NOT via views.py -- to avoid
        circular imports and premature module-level side-effects."""
        try:
            from .nlp_processor import MedicalNLPProcessor
            p = MedicalNLPProcessor()
            p._get_all_symptoms()
            p._get_emergency_keywords()
            logger.info("NLP caches pre-warmed")
        except Exception as exc:
            logger.warning("NLP warm-up skipped: %s", exc)
