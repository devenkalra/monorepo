from django.urls import path

from .views import LinkRedirectDetailView, LinkRedirectListCreateView

urlpatterns = [
    path('', LinkRedirectListCreateView.as_view(), name='link-redirect-list'),
    path('<int:pk>/', LinkRedirectDetailView.as_view(), name='link-redirect-detail'),
]
