"""URL configuration for the accounts application."""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("password-reset/", views.AppPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.AppPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        views.AppPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        views.AppPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
