from django.urls import path

from .views import LocationSearchView, TripCalculateView

urlpatterns = [
    path("trips/locations/search/", LocationSearchView.as_view(), name="location-search"),
    path("trips/calculate/", TripCalculateView.as_view(), name="trip-calculate"),
]
