from django.urls import path

from .views import HealthView, TripPlanView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('trip/plan/', TripPlanView.as_view(), name='trip-plan'),
]
