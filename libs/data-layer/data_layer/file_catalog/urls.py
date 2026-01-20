from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FileViewSet, FolderViewSet, TaskViewSet, CatalogIngestView

router = DefaultRouter()
router.register(r'files', FileViewSet)
router.register(r'folders', FolderViewSet)
router.register(r'tasks', TaskViewSet)  # Register the Task endpoint

urlpatterns = [
    path('', include(router.urls)),
    path('catalog/ingest/', CatalogIngestView.as_view(), name='catalog_ingest'),
]
