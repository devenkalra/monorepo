from django.db import models


class AudioTrack(models.Model):
    folder_slug = models.CharField(max_length=64, db_index=True)
    relpath = models.CharField(max_length=1000)
    parent = models.CharField(max_length=1000, blank=True, default='', db_index=True)
    filename = models.CharField(max_length=255)
    title = models.CharField(max_length=500, blank=True, default='')
    artist = models.CharField(max_length=500, blank=True, default='')
    composer = models.CharField(max_length=500, blank=True, default='')
    genre = models.CharField(max_length=255, blank=True, default='')
    album = models.CharField(max_length=500, blank=True, default='')
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    bpm = models.FloatField(null=True, blank=True)
    has_cover = models.BooleanField(default=False)
    duration_seconds = models.FloatField(null=True, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    mtime = models.DateTimeField(null=True, blank=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['folder_slug', 'relpath']
        constraints = [
            models.UniqueConstraint(
                fields=['folder_slug', 'relpath'],
                name='audiotrack_folder_relpath',
            ),
        ]
        indexes = [
            models.Index(fields=['artist'], name='audiotrack_artist_idx'),
            models.Index(fields=['album'], name='audiotrack_album_idx'),
            models.Index(fields=['genre'], name='audiotrack_genre_idx'),
            models.Index(fields=['year'], name='audiotrack_year_idx'),
            models.Index(fields=['composer'], name='audiotrack_composer_idx'),
        ]

    def __str__(self):
        return self.title or self.filename
