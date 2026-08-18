from django.contrib import admin

from .models import AudioTrack


@admin.register(AudioTrack)
class AudioTrackAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'artist', 'composer', 'genre', 'year', 'bpm', 'has_cover',
        'album', 'folder_slug', 'filename', 'duration_seconds', 'indexed_at',
    )
    list_filter = ('folder_slug', 'genre', 'year')
    search_fields = ('title', 'artist', 'composer', 'genre', 'album', 'filename', 'relpath')
    readonly_fields = (
        'folder_slug', 'relpath', 'filename', 'title', 'artist', 'composer',
        'genre', 'album', 'year', 'bpm', 'has_cover',
        'duration_seconds', 'size_bytes', 'mtime', 'indexed_at',
    )

    def has_add_permission(self, request):
        return False
