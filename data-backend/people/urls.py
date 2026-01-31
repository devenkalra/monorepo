from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PersonViewSet, NoteViewSet, LocationViewSet, MovieViewSet, BookViewSet,
    ContainerViewSet, AssetViewSet, OrgViewSet, EntityViewSet, EntityRelationViewSet,
    UploadViewSet, SearchViewSet, TagViewSet, RecentEntityViewSet
)

router = DefaultRouter()
router.register(r'entities', EntityViewSet, basename='entity')
router.register(r'people', PersonViewSet, basename='person')
router.register(r'notes', NoteViewSet, basename='note')
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'movies', MovieViewSet, basename='movie')
router.register(r'books', BookViewSet, basename='book')
router.register(r'containers', ContainerViewSet, basename='container')
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'orgs', OrgViewSet, basename='org')
router.register(r'relations', EntityRelationViewSet, basename='entityrelation')
router.register(r'upload', UploadViewSet, basename='upload')
router.register(r'search', SearchViewSet, basename='search')
router.register(r'tags', TagViewSet, basename='tag')

# Add explicit path for recent entities (not using router to avoid conflict)
from django.urls import path
urlpatterns = [
    path('entities/recent/', RecentEntityViewSet.as_view({'get': 'list'}), name='entity-recent'),
    path('', include(router.urls)),
]

