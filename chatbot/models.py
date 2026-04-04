# chatbot/models.py
import uuid

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class Disease(models.Model):
    name            = models.CharField(max_length=200)
    description     = models.TextField()
    common_symptoms = models.TextField(help_text="Comma-separated symptom list")
    search_vector   = SearchVectorField(null=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return self.name


class Symptom(models.Model):
    name              = models.CharField(max_length=100, unique=True)
    alternative_names = models.TextField(blank=True, help_text="Comma-separated variations")
    diseases          = models.ManyToManyField(Disease, related_name="symptoms", blank=True)

    def __str__(self):
        return self.name


class FirstAidProcedure(models.Model):
    disease           = models.ForeignKey(Disease, on_delete=models.CASCADE,
                                          related_name="first_aid_procedures")
    title             = models.CharField(max_length=200)
    steps             = models.TextField(help_text="Step-by-step instructions (markdown)")
    warning_notes     = models.TextField(blank=True)
    when_to_seek_help = models.TextField()

    def __str__(self):
        return f"{self.disease.name}: {self.title}"


class EmergencyKeyword(models.Model):
    SEVERITY_CHOICES = [
        ("CRITICAL", "Immediate Emergency"),
        ("URGENT",   "Seek Care Within Hours"),
        ("CAUTION",  "Monitor Carefully"),
    ]
    keyword          = models.CharField(max_length=100, unique=True)
    severity         = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    response_message = models.TextField(help_text="Message shown to the user")

    def __str__(self):
        return f"{self.keyword} ({self.severity})"


class UserProfile(models.Model):
    AGE_CHOICES = [
        ("0-12",    "Child (0-12)"),
        ("13-17",   "Teen (13-17)"),
        ("18-35",   "Young Adult (18-35)"),
        ("36-50",   "Adult (36-50)"),
        ("51+",     "Senior (51+)"),
        ("unknown", "Prefer not to say"),
    ]
    GENDER_CHOICES = [
        ("male",    "Male"),
        ("female",  "Female"),
        ("other",   "Other"),
        ("unknown", "Prefer not to say"),
    ]

    user           = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id     = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    age_group      = models.CharField(max_length=20, choices=AGE_CHOICES, default="unknown")
    gender         = models.CharField(max_length=20, choices=GENDER_CHOICES, default="unknown")
    location       = models.CharField(max_length=200, blank=True,
                                      help_text="City / Region in Kenya")
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    user_agent     = models.TextField(blank=True)
    first_seen     = models.DateTimeField(auto_now_add=True)
    last_seen      = models.DateTimeField(auto_now=True)
    total_sessions = models.IntegerField(default=1)

    def __str__(self):
        return f"{str(self.session_id)[:8]}… ({self.first_seen.date()})"


class ChatSession(models.Model):
    session_id    = models.CharField(max_length=100, unique=True)
    user_profile  = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                      null=True, blank=True, related_name="chat_sessions")
    created_at    = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.session_id[:8]}… ({self.created_at.date()})"


class ChatMessage(models.Model):
    ROLE_CHOICES = [("user", "User"), ("bot", "Bot")]

    session            = models.ForeignKey(ChatSession, on_delete=models.CASCADE,
                                           related_name="messages")
    user_profile       = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                           null=True, blank=True, related_name="chat_messages")
    role               = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content            = models.TextField()
    timestamp          = models.DateTimeField(auto_now_add=True)
    emergency_detected = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class SymptomLog(models.Model):
    user_profile     = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                         related_name="symptom_logs")
    symptoms         = models.JSONField()
    raw_input        = models.TextField()
    matched_diseases = models.JSONField(default=list)
    timestamp        = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        syms = self.symptoms[:3] if isinstance(self.symptoms, list) else []
        return f"{self.user_profile} — {', '.join(syms)}"


class EmergencyLog(models.Model):
    user_profile           = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                                related_name="emergency_logs")
    emergency_keywords     = models.JSONField()
    severity               = models.CharField(max_length=20)
    raw_input              = models.TextField()
    location_shared        = models.BooleanField(default=False)
    latitude               = models.FloatField(null=True, blank=True)
    longitude              = models.FloatField(null=True, blank=True)
    nearby_hospitals_shown = models.IntegerField(default=0)
    timestamp              = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_profile} — {self.severity}: {self.emergency_keywords}"


class FirstAidFeedback(models.Model):
    RATING_CHOICES = [
        (1, "1 — Not Helpful"),
        (2, "2 — Somewhat Helpful"),
        (3, "3 — Helpful"),
        (4, "4 — Very Helpful"),
        (5, "5 — Extremely Helpful"),
    ]

    user_profile   = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                       related_name="feedback")
    symptom_log    = models.ForeignKey(SymptomLog, on_delete=models.SET_NULL,
                                       null=True, blank=True)
    disease_name   = models.CharField(max_length=200)
    response_given = models.TextField(blank=True)
    rating         = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    feedback_text  = models.TextField(blank=True)
    timestamp      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_profile} — {self.disease_name}: {self.rating}"


class ChatAnalytics(models.Model):
    date                 = models.DateField(unique=True)
    total_users          = models.IntegerField(default=0)
    new_users            = models.IntegerField(default=0)
    returning_users      = models.IntegerField(default=0)
    total_messages       = models.IntegerField(default=0)
    emergency_detections = models.IntegerField(default=0)
    location_shares      = models.IntegerField(default=0)
    average_rating       = models.FloatField(default=0.0)
    top_diseases         = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return str(self.date)
