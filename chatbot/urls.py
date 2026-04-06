# chatbot/urls.py
# FIX: view names in urls.py didn't match the actual function names in views.py
#   views.chat_view      → views.process_message
#   views.hospitals_view → views.get_nearby_hospitals
#   views.feedback_view  → views.submit_feedback
# This caused AttributeError at URL-conf load time, crashing ALL endpoints
# including /api/health/, producing 500 on every request.

from django.urls import path
from . import views

urlpatterns = [
    path('chat/',      views.process_message,        name='chat'),
    path('hospitals/', views.get_nearby_hospitals,   name='hospitals'),
    path('feedback/',  views.submit_feedback,        name='feedback'),
    path('health/',    views.health_check,           name='health'),
]
