# chatbot/admin.py
from django.contrib import admin

from .models import (
    ChatAnalytics, ChatMessage, ChatSession,
    Disease, EmergencyKeyword, EmergencyLog,
    FirstAidFeedback, FirstAidProcedure,
    Symptom, SymptomLog, UserProfile,
)


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display  = ("name", "created_at", "symptom_count")
    search_fields = ("name", "description", "common_symptoms")
    list_filter   = ("created_at",)

    def symptom_count(self, obj):
        try:
            return obj.symptoms.count()
        except Exception:
            return 0
    symptom_count.short_description = "Symptoms"


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display      = ("name", "disease_list")
    search_fields     = ("name", "alternative_names")
    filter_horizontal = ("diseases",)

    def disease_list(self, obj):
        try:
            return ", ".join(d.name for d in obj.diseases.all()[:3])
        except Exception:
            return ""
    disease_list.short_description = "Diseases"


@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display  = ("title", "disease", "steps_preview")
    search_fields = ("title", "steps", "disease__name")
    list_filter   = ("disease",)

    def steps_preview(self, obj):
        s = obj.steps or ""
        return s[:60] + ("…" if len(s) > 60 else "")
    steps_preview.short_description = "Steps"


@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display  = ("keyword", "severity", "response_preview")
    search_fields = ("keyword", "response_message")
    list_filter   = ("severity",)

    def response_preview(self, obj):
        return (obj.response_message or "")[:60] + "…"
    response_preview.short_description = "Response"


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display    = ("session_id", "created_at", "last_activity", "message_count")
    search_fields   = ("session_id",)
    list_filter     = ("created_at",)
    readonly_fields = ("session_id", "created_at", "last_activity")

    def message_count(self, obj):
        try:
            return obj.messages.count()
        except Exception:
            return 0
    message_count.short_description = "Messages"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display    = ("session", "role", "timestamp", "emergency_detected", "content_preview")
    search_fields   = ("content",)
    list_filter     = ("role", "emergency_detected", "timestamp")
    readonly_fields = ("session", "role", "content", "timestamp", "emergency_detected")

    def content_preview(self, obj):
        return (obj.content or "")[:60] + "…"
    content_preview.short_description = "Content"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display    = ("short_session", "age_group", "gender", "location",
                       "first_seen", "last_seen", "total_sessions")
    list_filter     = ("age_group", "gender", "first_seen")
    search_fields   = ("session_id", "location")
    readonly_fields = ("session_id", "ip_address", "user_agent", "first_seen", "last_seen")

    def short_session(self, obj):
        s = str(obj.session_id or "")
        return s[:8] + "…" if len(s) > 8 else s
    short_session.short_description = "Session"


@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display    = ("user_profile", "symptoms_preview", "timestamp", "match_count")
    list_filter     = ("timestamp",)
    search_fields   = ("raw_input",)
    readonly_fields = ("user_profile", "symptoms", "raw_input", "matched_diseases", "timestamp")

    def symptoms_preview(self, obj):
        try:
            syms = obj.symptoms[:3] if isinstance(obj.symptoms, list) else []
            return ", ".join(str(s) for s in syms)
        except Exception:
            return ""
    symptoms_preview.short_description = "Symptoms"

    def match_count(self, obj):
        try:
            return len(obj.matched_diseases or [])
        except Exception:
            return 0
    match_count.short_description = "Matches"


@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display  = ("user_profile", "severity", "keywords_preview",
                     "location_shared", "timestamp")
    list_filter   = ("severity", "location_shared", "timestamp")
    search_fields = ("raw_input",)

    def keywords_preview(self, obj):
        try:
            kws = obj.emergency_keywords[:3] if isinstance(obj.emergency_keywords, list) else []
            return ", ".join(str(k) for k in kws)
        except Exception:
            return ""
    keywords_preview.short_description = "Keywords"


@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display  = ("user_profile", "disease_name", "rating", "timestamp")
    list_filter   = ("rating", "timestamp")
    search_fields = ("disease_name", "feedback_text")


@admin.register(ChatAnalytics)
class ChatAnalyticsAdmin(admin.ModelAdmin):
    list_display  = ("date", "total_users", "new_users", "returning_users",
                     "total_messages", "emergency_detections", "average_rating")
    list_filter   = ("date",)
    readonly_fields = (
        "date", "total_users", "new_users", "returning_users",
        "total_messages", "emergency_detections", "location_shares",
        "average_rating", "top_diseases",
  )
