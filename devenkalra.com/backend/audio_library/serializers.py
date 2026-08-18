from rest_framework import serializers

from .models import AudioTrack
from .roots import configured_roots, stream_signature


class AudioTrackSerializer(serializers.ModelSerializer):
    folder_label = serializers.SerializerMethodField()
    stream_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = AudioTrack
        fields = [
            'id', 'folder_slug', 'folder_label', 'relpath', 'parent',
            'filename', 'title', 'artist', 'composer', 'genre', 'album',
            'year', 'bpm', 'has_cover', 'duration_seconds', 'size_bytes', 'mtime',
            'stream_url', 'cover_url',
        ]

    def get_folder_label(self, obj):
        root = next((row for row in configured_roots() if row['slug'] == obj.folder_slug), None)
        return (root or {}).get('label') or obj.folder_slug

    def get_stream_url(self, obj):
        return f'/api/audio/tracks/{obj.id}/stream/?sig={stream_signature(obj.id)}'

    def get_cover_url(self, obj):
        if not obj.has_cover:
            return ''
        return f'/api/audio/tracks/{obj.id}/cover/?sig={stream_signature(obj.id)}'
