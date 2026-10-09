"""User profile model."""
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    THEME_CHOICES = [("dark", "Dark"), ("light", "Light")]
    LEVEL_CHOICES = [
        ("low", "Low compression"),
        ("medium", "Medium compression"),
        ("high", "High compression"),
        ("custom", "Custom"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    preferred_level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default="medium")
    preferred_theme = models.CharField(max_length=8, choices=THEME_CHOICES, default="dark")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile for {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
