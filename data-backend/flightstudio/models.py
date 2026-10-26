from django.conf import settings
from django.db import models


class FlightPath(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='flightstudio_paths',
    )
    path_id = models.CharField(max_length=64)
    document = models.JSONField(default=dict)
    # Segment program (§ SEGMENT_MODEL.md). When set, this row is a program
    # path: ``document`` stays empty (or a stub) and preview reads ``program``.
    # The two document types coexist at rest; waypoint paths leave this null.
    program = models.JSONField(null=True, blank=True, default=None)
    map_overlay = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['path_id']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'path_id'], name='fs_owner_path_id_uniq'),
        ]
        indexes = [
            models.Index(fields=['owner', 'path_id']),
        ]

    def __str__(self):
        return self.path_id
