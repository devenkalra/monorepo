"""CAD URL configuration."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from . import views

# Wrap static file views with auth
serve_texture = api_view(["GET"])(permission_classes([IsAuthenticated])(views.serve_texture))
serve_env = api_view(["GET"])(permission_classes([IsAuthenticated])(views.serve_env))

router = DefaultRouter()
router.register(r"models", views.CADModelViewSet, basename="cadmodel")
router.register(r"scenes", views.SceneConfigViewSet, basename="sceneconfig")

# Explicit path without trailing slash so POST to /render works (Django APPEND_SLASH
# would redirect and lose POST data)
urlpatterns = [
    path(
        "models/<int:pk>/render",
        views.CADModelViewSet.as_view({"post": "render"}),
        name="cadmodel-render-noslash",
    ),
    path("", include(router.urls)),
    path("textures/<path:filename>", serve_texture, name="cad-texture"),
    path("env/<path:filename>", serve_env, name="cad-env"),
]
