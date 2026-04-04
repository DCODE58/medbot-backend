# chatbot/analytics.py
import logging
from datetime import timedelta

from django.db.models import Avg, Q
from django.utils import timezone

from .models import (
    ChatAnalytics, ChatMessage, EmergencyLog,
    FirstAidFeedback, SymptomLog, UserProfile,
)

logger = logging.getLogger(__name__)


def generate_daily_analytics(target_date=None):
    """
    Aggregate metrics for `target_date` (defaults to yesterday).
    Creates or updates a ChatAnalytics row for that date.
    Returns the ChatAnalytics instance.
    """
    if target_date is None:
        target_date = timezone.now().date() - timedelta(days=1)

    analytics, _ = ChatAnalytics.objects.get_or_create(date=target_date)

    try:
        analytics.total_users = UserProfile.objects.filter(
            last_seen__date__lte=target_date
        ).count()

        analytics.new_users = UserProfile.objects.filter(
            first_seen__date=target_date
        ).count()

        analytics.returning_users = UserProfile.objects.filter(
            first_seen__date__lt=target_date,
            last_seen__date=target_date,
        ).count()

        analytics.total_messages = ChatMessage.objects.filter(
            timestamp__date=target_date
        ).count()

        analytics.emergency_detections = EmergencyLog.objects.filter(
            timestamp__date=target_date
        ).count()

        analytics.location_shares = EmergencyLog.objects.filter(
            Q(timestamp__date=target_date) & Q(location_shared=True)
        ).count()

        avg = FirstAidFeedback.objects.filter(
            timestamp__date=target_date,
            rating__isnull=False,
        ).aggregate(avg=Avg("rating"))["avg"]
        analytics.average_rating = round(avg, 2) if avg else 0.0

        disease_counts: dict = {}
        for log in SymptomLog.objects.filter(timestamp__date=target_date).only("matched_diseases"):
            matched = log.matched_diseases
            if not matched:
                continue
            try:
                for item in (matched if isinstance(matched, list) else []):
                    name = item.get("name") if isinstance(item, dict) else None
                    if name:
                        disease_counts[name] = disease_counts.get(name, 0) + 1
            except Exception as exc:
                logger.warning("analytics: failed to parse matched_diseases — %s", exc)

        analytics.top_diseases = dict(
            sorted(disease_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        analytics.save()
        logger.info("Daily analytics generated for %s", target_date)
        return analytics

    except Exception as exc:
        logger.error("generate_daily_analytics failed: %s", exc, exc_info=True)
        raise
