"""CAD serializers."""

from rest_framework import serializers
from .models import CADModel
from .utils import extract_parameters


class CADModelSerializer(serializers.ModelSerializer):
    parameters = serializers.SerializerMethodField()

    class Meta:
        model = CADModel
        fields = ["id", "name", "script", "parameters", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_parameters(self, obj):
        return extract_parameters(obj.script)
