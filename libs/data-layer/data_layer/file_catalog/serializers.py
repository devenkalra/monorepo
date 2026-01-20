from rest_framework import serializers
from .models import File

class FileSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)

        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    # Optional: Add a calculated field for human-readable size
    size_mb = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            'id',
            'volume',
            'path',
            'name',
            'hash',
            'size',
            'size_mb',
            'last_seen',
            'thumbnail'
        ]

    def get_size_mb(self, obj):
        if obj.size:
            return round(obj.size / (1024 * 1024), 2)
        return 0.0