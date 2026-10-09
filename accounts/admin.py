"""Admin configuration for the accounts app."""
from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_level", "preferred_theme", "created_at")
    list_filter = ("preferred_level", "preferred_theme")
    search_fields = ("user__username", "user__email")
