from django.urls import path
from . import views

urlpatterns = [
    path("chat/",      views.process_message,     name="process_message"),
    path("hospitals/", views.get_nearby_hospitals, name="get_nearby_hospitals"),
    path("feedback/",  views.submit_feedback,      name="submit_feedback"),
    path("health/",    views.health_check,         name="health_check"),
]
