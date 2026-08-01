from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MenuView, LoginView, LogoutView, AuthStatusView, CSRFTokenView,
    ProjectViewSet, WorkflowIdeaViewSet, BookReviewViewSet, MusicTrackViewSet, RecipeViewSet,
    PageDataDetailView, ClickUpTasksView, ClickUpContactsView, ClickUpContactActivitiesView,
    BlogCategoryViewSet, BlogTagViewSet, BlogPostViewSet, BlogCommentView,
    SocialAuthConfigView, SocialGoogleLoginView, SocialGithubLoginView,
    PageViewSet, MenuItemViewSet, NoteNodeViewSet,
)

router = DefaultRouter()
router.register(r'pages', PageViewSet, basename='page')
router.register(r'menu-items', MenuItemViewSet, basename='menu-item')
router.register(r'note-nodes', NoteNodeViewSet, basename='note-node')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'ideas', WorkflowIdeaViewSet, basename='idea')
router.register(r'books', BookReviewViewSet, basename='book')
router.register(r'tracks', MusicTrackViewSet, basename='track')
router.register(r'recipes', RecipeViewSet, basename='recipe')
router.register(r'blog/categories', BlogCategoryViewSet, basename='blog-category')
router.register(r'blog/tags', BlogTagViewSet, basename='blog-tag')
router.register(r'blog/posts', BlogPostViewSet, basename='blog-post')

urlpatterns = [
    path('menu/', MenuView.as_view(), name='api-menu'),
    path('page-data/<slug:page_slug>/', PageDataDetailView.as_view(), name='api-page-data'),
    path('auth/login/', LoginView.as_view(), name='api-login'),
    path('auth/logout/', LogoutView.as_view(), name='api-logout'),
    path('auth/status/', AuthStatusView.as_view(), name='api-auth-status'),
    path('auth/csrf/', CSRFTokenView.as_view(), name='api-csrf'),
    path('auth/config/', SocialAuthConfigView.as_view(), name='api-social-config'),
    path('auth/social/google/', SocialGoogleLoginView.as_view(), name='api-social-google-login'),
    path('auth/social/github/', SocialGithubLoginView.as_view(), name='api-social-github-login'),
    path('clickup/tasks/', ClickUpTasksView.as_view(), name='api-clickup-tasks'),
    path('clickup/contacts/', ClickUpContactsView.as_view(), name='api-clickup-contacts'),
    path('clickup/contacts/<str:task_id>/activities/', ClickUpContactActivitiesView.as_view(), name='api-clickup-contact-activities'),
    path('blog/posts/<slug:post_slug>/comments/', BlogCommentView.as_view(), name='api-blog-comments'),
    path('', include(router.urls)),
]
