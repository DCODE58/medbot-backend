# chatbot/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_view, name='chat'),
    path('hospitals/', views.hospitals_view, name='hospitals'),
    path('feedback/', views.feedback_view, name='feedback'),
    path('health/', views.health_check, name='health'),
]
