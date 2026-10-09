"""URL configuration for the compressor application."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

app_name = "compressor"

router = DefaultRouter()
router.register("uploads", api.UploadedFileViewSet, basename="api-upload")
router.register("jobs", api.CompressionJobViewSet, basename="api-job")

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("image-compressor/", views.image_compressor_page, name="image_compressor"),
    path("document-compressor/", views.document_compressor_page, name="document_compressor"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("results/<int:pk>/", views.results, name="results"),
    # AJAX API
    path("api/upload/", views.upload_file, name="upload"),
    path("api/chunk-upload/", views.chunk_upload, name="chunk_upload"),
    path("api/compress/", views.compress_files, name="compress"),
    path("api/job/<int:pk>/status/", views.job_status, name="job_status"),
    path("api/jobs/", views.job_list, name="job_list"),
    path("api/download-all/", views.download_all, name="download_all"),
    # REST API
    path("api/rest/", include(router.urls)),
    # Secure file serving
    path("preview/original/<int:pk>/", views.preview_original, name="preview_original"),
    path("preview/<int:pk>/", views.preview, name="preview"),
    path("download/<int:pk>/", views.download_file, name="download"),
    # History management
    path("job/<int:pk>/delete/", views.delete_job, name="delete_job"),
    path("history/clear/", views.clear_history, name="clear_history"),
]
