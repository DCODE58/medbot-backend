import logging
import sys
import threading
import time

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "populate_kenya_data", "shell", "dbshell", "check", "test",
    "createcachetable",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatbot"

    def ready(self) -> None:
        # Skip warm-up for management commands
        argv = sys.argv or []
        if any(cmd in " ".join(argv) for cmd in _SKIP_COMMANDS):
            return

        # FIX: original check was `sys.argv[0]` (the script path) which never
        # contains "runserver" when invoked as `manage.py runserver`.
        # Under gunicorn sys.argv[0] is the gunicorn binary path — so the
        # original guard accidentally skipped warmup under gunicorn too on some
        # Render builds.  Use a join check instead.
        if "runserver" in " ".join(argv):
            return

        threading.Thread(target=self._delayed_warmup, daemon=True).start()

    def _delayed_warmup(self):
        time.sleep(5)
        self._retry_warmup(self._warm_rag, "RAG")
        self._retry_warmup(self._warm_nlp, "NLP")

    def _retry_warmup(self, func, name, retries=5, delay=3):
        for attempt in range(retries):
            try:
                func()
                logger.info("%s warm-up completed", name)
                return
            except Exception as exc:
                logger.warning("%s warm-up attempt %d failed: %s", name, attempt + 1, str(exc))
                time.sleep(delay)
        logger.error("%s warm-up FAILED after retries", name)

    def _warm_rag(self):
        from .rag_retriever import get_rag_retriever
        get_rag_retriever().warm_up()

    def _warm_nlp(self):
        from .nlp_processor import MedicalNLPProcessor
        processor = MedicalNLPProcessor()
        processor._get_all_symptoms()
        processor._get_emergency_keywords()
