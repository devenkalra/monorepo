from rest_framework import serializers

from gallery.models import Gallery, UserMedia
from vacation_list.models import VacList

from .models import Trip, TripDay, TripLodging, TripStop, TripMedia, TripStopAttachment


def _request_user(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user
    return None


def _set_pk_queryset(field, qs):
    field.queryset = qs
    child = getattr(field, 'child_relation', None)
    if child is not None:
        child.queryset = qs


class TripStopAttachmentSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    stop_id = serializers.PrimaryKeyRelatedField(
        queryset=TripStop.objects.none(),
        source='stop',
    )
    asset_id = serializers.PrimaryKeyRelatedField(
        queryset=UserMedia.objects.none(),
        source='asset',
        allow_null=True,
        required=False,
    )
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = TripStopAttachment
        fields = [
            'id', 'user', 'stop', 'stop_id', 'kind', 'title',
            'url', 'osm_url', 'address', 'lat', 'lng',
            'asset', 'asset_id', 'file_url', 'thumbnail_url',
            'sort_order', 'created_at', 'modified_on',
        ]
        read_only_fields = ['stop', 'asset']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user:
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(user=user))
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.filter(owner=user))
        else:
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.none())
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.none())

    def get_file_url(self, obj):
        if obj.asset_id:
            return obj.asset.url
        return obj.url

    def get_thumbnail_url(self, obj):
        if obj.asset_id:
            return obj.asset.thumbnail_url
        return ''

    def validate(self, attrs):
        kind = attrs.get('kind') or getattr(self.instance, 'kind', None)
        url = attrs.get('url', getattr(self.instance, 'url', ''))
        address = attrs.get('address', getattr(self.instance, 'address', ''))
        lat = attrs.get('lat', getattr(self.instance, 'lat', None))
        lng = attrs.get('lng', getattr(self.instance, 'lng', None))
        asset = attrs.get('asset', getattr(self.instance, 'asset', None))
        if kind == TripStopAttachment.KIND_LOCATION:
            if not (url or address or (lat is not None and lng is not None)):
                raise serializers.ValidationError('Location needs an address, coordinates, or map URL.')
        elif kind in (TripStopAttachment.KIND_DOCUMENT, TripStopAttachment.KIND_PICTURE):
            if not (url or asset):
                raise serializers.ValidationError('Upload a file or provide a URL.')
        elif kind == TripStopAttachment.KIND_URL and not url:
            raise serializers.ValidationError('URL is required.')
        return attrs

    def create(self, validated_data):
        item = TripStopAttachment(**validated_data)
        item.fill_map_urls()
        item.save()
        return item

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.fill_map_urls()
        instance.save()
        return instance


class TripStopSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    day_id = serializers.PrimaryKeyRelatedField(
        queryset=TripDay.objects.none(),
        source='day',
        required=False,
    )
    attachments = TripStopAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TripStop
        fields = [
            'id', 'user', 'day', 'day_id', 'text', 'loc', 'cat',
            'status', 'done', 'start_time', 'duration_minutes',
            'extra', 'sort_order', 'attachments',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['day']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        days = TripDay.objects.filter(user=user) if user else TripDay.objects.none()
        _set_pk_queryset(self.fields['day_id'], days)


class TripMediaSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    asset_id = serializers.PrimaryKeyRelatedField(
        queryset=UserMedia.objects.none(),
        source='asset',
    )
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        allow_null=True,
        required=False,
    )
    day_id = serializers.PrimaryKeyRelatedField(
        queryset=TripDay.objects.none(),
        source='day',
        allow_null=True,
        required=False,
    )
    stop_id = serializers.PrimaryKeyRelatedField(
        queryset=TripStop.objects.none(),
        source='stop',
        allow_null=True,
        required=False,
    )
    url = serializers.CharField(source='asset.url', read_only=True)
    thumbnail_url = serializers.CharField(source='asset.thumbnail_url', read_only=True)
    filename = serializers.CharField(source='asset.filename', read_only=True)

    class Meta:
        model = TripMedia
        fields = [
            'id', 'user', 'asset', 'asset_id',
            'trip', 'trip_id', 'day', 'day_id', 'stop', 'stop_id',
            'caption', 'sort_order', 'url', 'thumbnail_url', 'filename',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['asset', 'trip', 'day', 'stop']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user:
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.filter(owner=user))
            _set_pk_queryset(self.fields['trip_id'], Trip.objects.filter(user=user))
            _set_pk_queryset(self.fields['day_id'], TripDay.objects.filter(user=user))
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(user=user))
        else:
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.none())
            _set_pk_queryset(self.fields['trip_id'], Trip.objects.none())
            _set_pk_queryset(self.fields['day_id'], TripDay.objects.none())
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.none())


class TripLodgingSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    day_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )
    assigned_day_ids = serializers.PrimaryKeyRelatedField(
        source='days',
        many=True,
        read_only=True,
    )
    maps_url = serializers.CharField(read_only=True)
    day_count = serializers.IntegerField(source='days.count', read_only=True)

    class Meta:
        model = TripLodging
        fields = [
            'id', 'user', 'trip', 'trip_id', 'name', 'address', 'phone', 'url',
            'confirmation', 'notes', 'check_in_time', 'check_out_time',
            'day_ids', 'assigned_day_ids', 'maps_url', 'day_count',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = Trip.objects.filter(user=user) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)

    def _assign_days(self, lodging, day_ids):
        user = _request_user(self)
        days = list(TripDay.objects.filter(user=user, trip=lodging.trip, pk__in=day_ids))
        if len(days) != len(set(day_ids)):
            raise serializers.ValidationError({'day_ids': 'One or more days are not on this trip.'})
        lodging.days.exclude(pk__in=day_ids).update(lodging=None)
        TripDay.objects.filter(pk__in=[d.pk for d in days]).update(lodging=lodging)

    def create(self, validated_data):
        day_ids = validated_data.pop('day_ids', None)
        lodging = TripLodging.objects.create(**validated_data)
        if day_ids is not None:
            self._assign_days(lodging, day_ids)
        return lodging

    def update(self, instance, validated_data):
        day_ids = validated_data.pop('day_ids', None)
        lodging = super().update(instance, validated_data)
        if day_ids is not None:
            self._assign_days(lodging, day_ids)
        return lodging


class TripLodgingSummarySerializer(serializers.ModelSerializer):
    maps_url = serializers.CharField(read_only=True)

    class Meta:
        model = TripLodging
        fields = [
            'id', 'name', 'address', 'phone', 'url', 'confirmation',
            'notes', 'check_in_time', 'check_out_time', 'maps_url',
        ]


class TripDaySerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    lodging_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLodging.objects.none(),
        source='lodging',
        allow_null=True,
        required=False,
    )
    lodging = TripLodgingSummarySerializer(read_only=True)
    stops = TripStopSerializer(many=True, read_only=True)
    media = TripMediaSerializer(many=True, read_only=True)
    stop_count = serializers.IntegerField(source='stops.count', read_only=True)

    class Meta:
        model = TripDay
        fields = [
            'id', 'user', 'trip', 'trip_id', 'date', 'title', 'journal',
            'lodging', 'lodging_id',
            'sort_order', 'stops', 'media', 'stop_count',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip', 'lodging']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = Trip.objects.filter(user=user) if user else Trip.objects.none()
        lodgings = TripLodging.objects.filter(user=user) if user else TripLodging.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['lodging_id'], lodgings)

    def validate(self, attrs):
        lodging = attrs.get('lodging')
        trip = attrs.get('trip') or getattr(self.instance, 'trip', None)
        if lodging and trip and lodging.trip_id != trip.id:
            raise serializers.ValidationError({'lodging_id': 'Lodging must belong to this trip.'})
        return attrs


class TripSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    packing_list_id = serializers.PrimaryKeyRelatedField(
        queryset=VacList.objects.none(),
        source='packing_list',
        allow_null=True,
        required=False,
    )
    gallery_id = serializers.PrimaryKeyRelatedField(
        queryset=Gallery.objects.none(),
        source='gallery',
        allow_null=True,
        required=False,
    )
    days = TripDaySerializer(many=True, read_only=True)
    lodgings = TripLodgingSerializer(many=True, read_only=True)
    day_count = serializers.IntegerField(source='days.count', read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'user', 'title', 'start_date', 'end_date',
            'packing_list', 'packing_list_id',
            'gallery', 'gallery_id',
            'days', 'lodgings', 'day_count',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['packing_list', 'gallery']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user:
            _set_pk_queryset(self.fields['packing_list_id'], VacList.objects.filter(user=user))
            _set_pk_queryset(self.fields['gallery_id'], Gallery.objects.filter(owner=user))
        else:
            _set_pk_queryset(self.fields['packing_list_id'], VacList.objects.none())
            _set_pk_queryset(self.fields['gallery_id'], Gallery.objects.none())


class TripListSerializer(TripSerializer):
    class Meta(TripSerializer.Meta):
        fields = [
            'id', 'user', 'title', 'start_date', 'end_date',
            'packing_list', 'packing_list_id',
            'gallery', 'gallery_id',
            'day_count',
            'created_at', 'modified_on',
        ]
