import logging
import sys
import threading
import time

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_SKIP_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic",
    "populate_kenya_data", "shell", "dbshell",
    "check", "test", "createcachetable",
})


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatbot"

    def ready(self) -> None:
        argv_str = " ".join(sys.argv or [])
        if any(cmd in argv_str for cmd in _SKIP_COMMANDS):
            return
        if "runserver" in argv_str:
            return
        threading.Thread(target=self._delayed_warmup, daemon=True).start()

    def _delayed_warmup(self):
        # Give gunicorn workers time to stabilise before hitting the DB
        time.sleep(6)
        self._retry(self._ensure_data_seeded,  "seed-check",  retries=6, delay=5)
        self._retry(self._warm_rag,             "RAG warmup",  retries=5, delay=3)
        self._retry(self._warm_nlp,             "NLP warmup",  retries=5, delay=3)

    # ── retry wrapper ────────────────────────────────────────────────────────

    def _retry(self, func, name, retries=5, delay=3):
        for attempt in range(1, retries + 1):
            try:
                func()
                logger.info("%s completed on attempt %d", name, attempt)
                return
            except Exception as exc:
                logger.warning("%s attempt %d/%d failed: %s", name, attempt, retries, exc)
                if attempt < retries:
                    time.sleep(delay)
        logger.error("%s FAILED after %d attempts", name, retries)

    # ── data seed check ──────────────────────────────────────────────────────

    def _ensure_data_seeded(self):
        """
        If the Disease table is empty (populate_kenya_data was skipped or
        crashed during the build step), run it now so the app works on first
        request.  This is the safety net for Render free-tier build quirks.
        """
        from .models import Disease
        count = Disease.objects.count()
        if count == 0:
            logger.warning(
                "Disease table is empty — running populate_kenya_data now"
            )
            from django.core.management import call_command
            call_command("populate_kenya_data", force=True)
            new_count = Disease.objects.count()
            logger.info("populate_kenya_data finished — %d diseases loaded", new_count)
        else:
            logger.info("Disease table OK — %d diseases present", count)

    # ── RAG warm-up ──────────────────────────────────────────────────────────

    def _warm_rag(self):
        from .rag_retriever import get_rag_retriever
        get_rag_retriever().warm_up()

    # ── NLP warm-up ──────────────────────────────────────────────────────────

    def _warm_nlp(self):
        from .nlp_processor import MedicalNLPProcessor
        p = MedicalNLPProcessor()
        p._get_all_symptoms()
        p._get_emergency_keywords()
