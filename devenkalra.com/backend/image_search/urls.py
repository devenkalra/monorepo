from django.urls import path

from .views import ImageDownloadView, ImageQualityView, ImageSearchView, ImageSizesView

urlpatterns = [
    path("search/", ImageSearchView.as_view(), name="image-search"),
    path("sizes/", ImageSizesView.as_view(), name="image-sizes"),
    path("quality/", ImageQualityView.as_view(), name="image-quality"),
    path("download/", ImageDownloadView.as_view(), name="image-download"),
]
