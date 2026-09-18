from django.conf import settings
from django.db import models

from .constants import ASSET_STATUSES, ASSET_STATUS_TODO, PRODUCTION_TYPES


class Production(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='productions',
    )
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True, default='')
    production_type = models.CharField(max_length=64, choices=PRODUCTION_TYPES)
    description = models.TextField(blank=True, default='')
    tags = models.JSONField(default=list, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-modified_on']
        indexes = [models.Index(fields=['user', 'is_archived'], name='prod_user_archived_idx')]

    def __str__(self):
        return self.title


class Scene(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='production_scenes',
    )
    production = models.ForeignKey(Production, on_delete=models.CASCADE, related_name='scenes')
    sort_order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255, blank=True, default='')
    scene_type = models.CharField(max_length=128, blank=True, default='')
    start_seconds = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    duration_seconds = models.DecimalField(max_digits=12, decimal_places=3, default=10)
    visuals = models.TextField(blank=True, default='')
    voiceover = models.TextField(blank=True, default='')
    music = models.TextField(blank=True, default='')
    fx_cues = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [models.Index(fields=['user', 'production'], name='prod_scene_user_prod_idx')]

    def __str__(self):
        label = self.title or self.scene_type or f'Scene {self.sort_order + 1}'
        return f'{self.production_id}: {label}'

    @property
    def end_seconds(self):
        return self.start_seconds + self.duration_seconds


class SceneAsset(models.Model):
    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name='assets')
    name = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name


class ProductionAssetStatus(models.Model):
    production = models.ForeignKey(
        Production,
        on_delete=models.CASCADE,
        related_name='asset_statuses',
    )
    name_key = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    status = models.CharField(max_length=24, choices=ASSET_STATUSES, default=ASSET_STATUS_TODO)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['production', 'name_key'],
                name='prod_asset_status_unique',
            ),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.status})'
