"""CAD models - user-owned parametric 3D models."""

from django.db import models
from django.contrib.auth.models import User


class CADModel(models.Model):
    """A parametric CAD model with script and parameters. Owned by a user."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cad_models", null=False
    )
    name = models.CharField(max_length=255)
    script = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.name} (user={self.user_id})"
