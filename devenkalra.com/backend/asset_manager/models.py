from django.db import models
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html


class AssetPhoto(models.Model):
    """Generic photo attached to AssetItem or AssetArea."""
    image = models.ImageField(upload_to='ass_photos/')
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text='Lower values appear first; the first image is used as the cover.',
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Asset photo'
        verbose_name_plural = 'Asset photos'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.description or f'Photo {self.pk}'

    def thumbnail_tag(self):
        if self.image and hasattr(self.image, 'url'):
            return format_html(
                '<img src="{}" style="max-height: 80px; max-width: 120px;" />',
                self.image.url,
            )
        return '(no image)'

    thumbnail_tag.short_description = 'Preview'


class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Asset category'
        verbose_name_plural = 'Asset categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class AssetTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Asset tag'
        verbose_name_plural = 'Asset tags'
        ordering = ['name']

    def __str__(self):
        return self.name


class AssetBase(models.Model):
    class LocatorType(models.TextChoices):
        LABEL = 'LABEL', 'Label'
        QR = 'QR', 'QR Code'
        EPC = 'EPC', 'EPC (RFID)'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_category_assets',
        help_text='High-level category (e.g. Camera Gear, Documents).',
    )
    tags = models.ManyToManyField(
        AssetTag,
        blank=True,
        related_name='%(app_label)s_%(class)s_tag_assets',
        help_text="Free-form tags, e.g. 'Canon', 'Travel'.",
    )
    locator_code = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Physical locator code printed or encoded with the item.',
    )
    locator_type = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        default='',
        choices=LocatorType.choices,
        help_text='Type of locator: Label, QR, or EPC.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    photos = GenericRelation(AssetPhoto, related_query_name='asset')

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class AssetArea(AssetBase):
    """Container that can nest inside another area (folder paradigm)."""
    parent_area = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_areas',
        help_text='Parent area (e.g. Garage for a shelf in the garage).',
    )

    class Meta:
        verbose_name = 'Asset area'
        verbose_name_plural = 'Asset areas'

    def full_path(self):
        parts = [self.name]
        node = self.parent_area
        seen = {self.pk}
        while node is not None and node.pk not in seen:
            parts.append(node.name)
            seen.add(node.pk)
            node = node.parent_area
        return ' / '.join(reversed(parts))


class AssetItem(AssetBase):
    """An item lives in an area, or is unlocated (orphan)."""
    area = models.ForeignKey(
        AssetArea,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='items',
        help_text='Area containing this item (optional orphan if blank).',
    )

    class Meta:
        verbose_name = 'Asset item'
        verbose_name_plural = 'Asset items'

    def full_path(self):
        if self.area_id:
            return f'{self.area.full_path()} / {self.name}'
        return self.name
