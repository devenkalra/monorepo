import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

# Top-level paths that must never become redirects (Django / SPA / infra).
RESERVED_SLUGS = frozenset({
    'admin', 'api', 'articles', 'assets', 'blog', 'docs', 'f', 'favicon',
    'login', 'media', 'p', 'redoc', 'robots', 'schema', 'sitemap', 'static',
})


def validate_slug(value):
    if not value or not SLUG_RE.match(value):
        raise ValidationError(
            'Use lowercase letters, digits, and hyphens only (e.g. rsvp).')
    if value in RESERVED_SLUGS:
        raise ValidationError(f'Slug "{value}" is reserved by the site.')


def validate_target_url(value):
    raw = (value or '').strip()
    if not raw:
        raise ValidationError('Target URL is required.')
    parsed = urlparse(raw)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValidationError('Target must be an absolute http(s) URL.')


class LinkRedirect(models.Model):
    """A public root short link: https://devenkalra.com/<slug> → target_url."""

    slug = models.SlugField(
        max_length=80, unique=True, validators=[validate_slug],
        help_text='Root path: https://devenkalra.com/<slug>',
    )
    title = models.CharField(max_length=255, blank=True, default='')
    target_url = models.URLField(max_length=2000, validators=[validate_target_url])
    is_public = models.BooleanField(
        default=True,
        help_text='Public links redirect without login.',
    )
    permanent = models.BooleanField(
        default=False,
        help_text='Use HTTP 301 when true; otherwise 302.',
    )
    hit_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Link redirect'
        verbose_name_plural = 'Link redirects'

    def __str__(self):
        return self.title or self.slug

    def clean(self):
        if self.slug:
            self.slug = self.slug.strip().lower()
            validate_slug(self.slug)
        if self.target_url:
            self.target_url = self.target_url.strip()
            validate_target_url(self.target_url)

    def save(self, *args, **kwargs):
        if self.slug:
            self.slug = self.slug.strip().lower()
        if self.target_url:
            self.target_url = self.target_url.strip()
        super().save(*args, **kwargs)

    @staticmethod
    def suggest_slug(name):
        base = slugify(name or '')[:60].strip('-') or 'link'
        if base in RESERVED_SLUGS:
            base = f'{base}-link'
        slug = base
        n = 2
        while LinkRedirect.objects.filter(slug=slug).exists() or slug in RESERVED_SLUGS:
            suffix = f'-{n}'
            slug = f'{base[:60 - len(suffix)]}{suffix}'
            n += 1
        return slug
