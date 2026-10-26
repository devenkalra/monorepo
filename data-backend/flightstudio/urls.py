from django.urls import path

from . import views

urlpatterns = [
    path('capabilities/', views.capabilities),
    path('locations/', views.locations),
    path('geocode/reverse/', views.geocode_reverse),
    path('geocode/', views.geocode_search),
    path('program/evaluate/', views.evaluate_program),
    path('program/preview/', views.preview_program_document),
    path('program/demos/', views.program_demos),
    path('paths/new/', views.new_path),
    path('paths/validate/', views.validate_document),
    path('paths/preview/', views.preview_document),
    path('paths/smooth-timing/', views.smooth_path_timing),
    path('paths/<str:path_id>/map/', views.path_map),
    path('paths/<str:path_id>/', views.path_detail),
    path('paths/', views.list_paths),
    path('earth-studio/', views.export_earth_studio),
    path('camera-orbit/', views.camera_orbit),
    path('cockpit-views/', views.sim_unavailable),
    path('cockpit-views/<path:rest>', views.sim_unavailable),
    path('simulation/<path:rest>', views.sim_unavailable),
    path('simflight/<path:rest>', views.sim_unavailable),
    path('autopilot/<path:rest>', views.sim_unavailable),
    path('autofly/<path:rest>', views.sim_unavailable),
]
