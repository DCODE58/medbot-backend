import logging
import sys
import threading
import time

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "populate_kenya_data", "shell", "dbshell", "check", "test",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatbot"

    def ready(self) -> None:
        # Skip warm-up for management commands
        if any(cmd in sys.argv for cmd in _SKIP_COMMANDS):
            return

        # IMPORTANT: avoid multiple threads in dev reloaders
        if sys.argv and "runserver" in sys.argv[0]:
            return

        threading.Thread(target=self._delayed_warmup, daemon=True).start()

    # ─────────────────────────────────────────────
    # SAFE DELAYED WARMUP
    # ─────────────────────────────────────────────

    def _delayed_warmup(self):
        """
        Wait for DB + migrations to stabilize,
        then safely warm up services.
        """

        time.sleep(5)

        # retry loop instead of blind execution
        self._retry_warmup(self._warm_rag, "RAG")
        self._retry_warmup(self._warm_nlp, "NLP")

    # ─────────────────────────────────────────────
    # RETRY WRAPPER (KEY FIX)
    # ─────────────────────────────────────────────

    def _retry_warmup(self, func, name, retries=5, delay=3):
        for attempt in range(retries):
            try:
                func()
                logger.info("%s warm-up completed", name)
                return

            except Exception as exc:
                logger.warning(
                    "%s warm-up attempt %d failed: %s",
                    name,
                    attempt + 1,
                    str(exc)
                )
                time.sleep(delay)

        logger.error("%s warm-up FAILED after retries", name)

    # ─────────────────────────────────────────────
    # RAG WARM-UP
    # ─────────────────────────────────────────────

    def _warm_rag(self):
        from .rag_retriever import get_rag_retriever
        get_rag_retriever().warm_up()

        logger.info("RAG warm-up triggered")

    # ─────────────────────────────────────────────
    # NLP WARM-UP
    # ─────────────────────────────────────────────

    def _warm_nlp(self):
        from .nlp_processor import MedicalNLPProcessor

        processor = MedicalNLPProcessor()
        processor._get_all_symptoms()
        processor._get_emergency_keywords()

        logger.info("NLP caches pre-warmed")
