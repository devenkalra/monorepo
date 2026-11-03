from django.urls import path

from .views import LinkMediaDetailView, LinkMediaListCreateView

urlpatterns = [
    path('', LinkMediaListCreateView.as_view(), name='link-media-list'),
    path('<int:pk>/', LinkMediaDetailView.as_view(), name='link-media-detail'),
]
