import re

from django.db import models
from django.utils.text import slugify

SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def validate_slug(value):
    from django.core.exceptions import ValidationError
    if not value or not SLUG_RE.match(value):
        raise ValidationError(
            'Use lowercase letters, digits, and hyphens only (e.g. ytf-flyer).')


class LinkMedia(models.Model):
    """A file served at a short public URL: /f/<slug>."""

    slug = models.SlugField(
        max_length=80, unique=True, validators=[validate_slug],
        help_text='Short path segment: https://devenkalra.com/f/<slug>',
    )
    title = models.CharField(max_length=255, blank=True, default='')
    file = models.FileField(upload_to='link_media/')
    content_type = models.CharField(max_length=128, blank=True, default='')
    byte_size = models.PositiveIntegerField(default=0)
    is_public = models.BooleanField(
        default=True,
        help_text='Public links are reachable without login (for email).',
    )
    download_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Link media'
        verbose_name_plural = 'Link media'

    def __str__(self):
        return self.title or self.slug

    def clean(self):
        if self.slug:
            self.slug = self.slug.strip().lower()
            validate_slug(self.slug)

    def save(self, *args, **kwargs):
        if self.slug:
            self.slug = self.slug.strip().lower()
        if self.file and not self.title:
            self.title = self.file.name.rsplit('/', 1)[-1]
        if self.file:
            try:
                self.byte_size = int(self.file.size or 0)
            except Exception:
                pass
        super().save(*args, **kwargs)

    @staticmethod
    def suggest_slug(name):
        base = slugify(name or '')[:60].strip('-') or 'file'
        slug = base
        n = 2
        while LinkMedia.objects.filter(slug=slug).exists():
            suffix = f'-{n}'
            slug = f'{base[:60 - len(suffix)]}{suffix}'
            n += 1
        return slug
