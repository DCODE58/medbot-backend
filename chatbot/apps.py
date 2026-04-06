import logging
import sys
import threading
import time

from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "populate_kenya_data", "shell", "dbshell", "check", "test",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatbot"

    def ready(self) -> None:
        # Skip warm-up during management commands
        if any(cmd in sys.argv for cmd in _SKIP_COMMANDS):
            return

        # Run warm-up in background to avoid blocking startup
        threading.Thread(target=self._delayed_warmup, daemon=True).start()

    # ── Delayed Warm-Up ───────────────────────────────────────────────────────

    def _delayed_warmup(self):
        """
        Delay warm-up slightly to allow:
        - DB connection to stabilize
        - migrations to complete
        - app to fully boot
        """
        time.sleep(5)

        self._warm_rag()
        self._warm_nlp()

    # ── Warm-Up: RAG ──────────────────────────────────────────────────────────

    def _warm_rag(self) -> None:
        try:
            from .rag_retriever import get_rag_retriever
            get_rag_retriever().warm_up()
            logger.info("RAG warm-up triggered")

        except (OperationalError, ProgrammingError) as exc:
            logger.warning("RAG warm-up skipped (DB not ready): %s", exc)

        except Exception as exc:
            logger.exception("Unexpected RAG warm-up failure: %s", exc)

    # ── Warm-Up: NLP ──────────────────────────────────────────────────────────

    def _warm_nlp(self) -> None:
        try:
            from .nlp_processor import MedicalNLPProcessor

            processor = MedicalNLPProcessor()
            processor._get_all_symptoms()
            processor._get_emergency_keywords()

            logger.info("NLP caches pre-warmed")

        except (OperationalError, ProgrammingError) as exc:
            logger.warning("NLP warm-up skipped (DB not ready): %s", exc)

        except Exception as exc:
            logger.exception("Unexpected NLP warm-up failure: %s", exc)
