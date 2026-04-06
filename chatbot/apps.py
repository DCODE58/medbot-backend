import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Management commands that should NOT trigger warm-up
_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "createcachetable", "populate_kenya_data",
    "shell", "dbshell", "check", "test",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "chatbot"

    def ready(self) -> None:
        if any(cmd in sys.argv for cmd in _SKIP_COMMANDS):
            return

        # Ensure the DB connection pool is ready before issuing any queries
        from django.db import connection
        try:
            connection.ensure_connection()
        except Exception as exc:
            logger.warning("DB not ready at startup -- skipping warm-up: %s", exc)
            return

        self._warm_rag()
        self._warm_nlp()

    def _warm_rag(self) -> None:
        try:
            from .rag_retriever import get_rag_retriever
            get_rag_retriever().warm_up()
        except Exception as exc:
            logger.error("RAG warm-up error: %s", exc)

    def _warm_nlp(self) -> None:
        """
        Prime NLP caches directly -- does NOT import views.py.
        Importing views at startup causes circular imports and triggers
        module-level side-effects (NLTK downloads, MedicalNLPProcessor init)
        before Django is fully ready, which silently crashes gunicorn workers
        and causes every request to return 500.
        """
        try:
            from .nlp_processor import MedicalNLPProcessor
            processor = MedicalNLPProcessor()
            processor._get_all_symptoms()
            processor._get_emergency_keywords()
            logger.info("NLP caches pre-warmed")
        except Exception as exc:
            logger.error("NLP warm-up error: %s", exc)
