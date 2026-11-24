import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

from gallery.models import Gallery, UserMedia
from vacation_list.models import VacList

from .access import (
    ROLE_OWNER,
    accessible_trips,
    is_trip_owner,
    owned_trips,
    trip_role,
    user_display_label,
)
from .models import (
    DEFAULT_CURRENCY,
    google_maps_url,
    Trip,
    TripComment,
    TripDay,
    TripLeg,
    TripLodging,
    TripMedia,
    TripShare,
    TripStop,
    TripStopAttachment,
    TripSuggestion,
    TripSuggestionBatch,
    TripTodo,
)


def _request_user(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user
    return None


def _zone(value):
    from .zones import is_zone

    value = (value or '').strip()
    if value and not is_zone(value):
        raise serializers.ValidationError(f'Unknown time zone "{value}".')
    return value


def _set_pk_queryset(field, qs):
    field.queryset = qs
    child = getattr(field, 'child_relation', None)
    if child is not None:
        child.queryset = qs


class PreserveOwnerMixin:
    """Prevent HiddenField(CurrentUserDefault) from overwriting owner on collaborator edits."""

    def update(self, instance, validated_data):
        validated_data.pop('user', None)
        return super().update(instance, validated_data)


class TripStopAttachmentSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    stop_id = serializers.PrimaryKeyRelatedField(
        queryset=TripStop.objects.none(),
        source='stop',
        allow_null=True,
        required=False,
    )
    lodging_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLodging.objects.none(),
        source='lodging',
        allow_null=True,
        required=False,
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
            'id', 'user', 'stop', 'stop_id', 'lodging', 'lodging_id', 'kind', 'title',
            'url', 'osm_url', 'address', 'lat', 'lng',
            'asset', 'asset_id', 'file_url', 'thumbnail_url',
            'sort_order', 'created_at', 'modified_on',
        ]
        read_only_fields = ['stop', 'lodging', 'asset']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user:
            trips = accessible_trips(user, write=True)
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(trip__in=trips))
            _set_pk_queryset(self.fields['lodging_id'], TripLodging.objects.filter(trip__in=trips))
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.filter(owner=user))
        else:
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.none())
            _set_pk_queryset(self.fields['lodging_id'], TripLodging.objects.none())
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
        stop = attrs.get('stop', getattr(self.instance, 'stop', None))
        lodging = attrs.get('lodging', getattr(self.instance, 'lodging', None))
        if bool(stop) == bool(lodging):
            raise serializers.ValidationError('Attach to a stop or a lodging, not both.')
        return attrs

    def create(self, validated_data):
        item = TripStopAttachment(**validated_data)
        item.fill_map_urls()
        item.save()
        return item

    def update(self, instance, validated_data):
        validated_data.pop('user', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.fill_map_urls()
        instance.save()
        return instance


class TripStopSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    day_id = serializers.PrimaryKeyRelatedField(
        queryset=TripDay.objects.none(),
        source='day',
        allow_null=True,
        required=False,
    )
    leg_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLeg.objects.none(),
        source='leg',
        allow_null=True,
        required=False,
    )
    attachments = TripStopAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TripStop
        fields = [
            'id', 'user', 'trip', 'trip_id', 'day', 'day_id', 'leg', 'leg_id',
            'kind', 'travel_mode', 'text',
            'description', 'loc', 'arrive_loc', 'cat', 'price', 'currency', 'person', 'confirmation',
            'status', 'done', 'start_time', 'duration_minutes', 'timezone', 'arrive_timezone',
            'extra', 'sort_order', 'attachments',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip', 'day', 'leg']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        days = TripDay.objects.filter(trip__in=trips) if user else TripDay.objects.none()
        legs = TripLeg.objects.filter(trip__in=trips) if user else TripLeg.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['day_id'], days)
        _set_pk_queryset(self.fields['leg_id'], legs)

    def validate_currency(self, value):
        code = (value or '').strip().upper()
        if code == DEFAULT_CURRENCY:
            return ''
        if code and not re.fullmatch(r'[A-Z]{3}', code):
            raise serializers.ValidationError('Use a 3-letter currency code such as THB.')
        return code

    def validate_person(self, value):
        return ' '.join((value or '').split())

    def validate_timezone(self, value):
        return _zone(value)

    def validate_arrive_timezone(self, value):
        return _zone(value)

    def validate(self, attrs):
        day = attrs.get('day', getattr(self.instance, 'day', None))
        leg = attrs.get('leg', getattr(self.instance, 'leg', None))
        trip = attrs.get('trip') or (day.trip if day else None) or (leg.trip if leg else None) or getattr(self.instance, 'trip', None)
        if trip is None:
            raise serializers.ValidationError({'trip_id': 'Provide a day or a trip.'})
        if day and day.trip_id != trip.id:
            raise serializers.ValidationError({'day_id': 'Day must belong to this trip.'})
        if leg and leg.trip_id != trip.id:
            raise serializers.ValidationError({'leg_id': 'Leg must belong to this trip.'})
        attrs['trip'] = trip
        kind = attrs.get('kind', getattr(self.instance, 'kind', TripStop.KIND_ACTIVITY))
        mode = attrs.get('travel_mode', getattr(self.instance, 'travel_mode', ''))
        if kind == TripStop.KIND_TRAVEL:
            valid = {choice[0] for choice in TripStop.TRAVEL_MODE_CHOICES}
            if mode not in valid:
                raise serializers.ValidationError(
                    {'travel_mode': 'Choose Flight, Drive, Walk, or Boat.'}
                )
        if kind == TripStop.KIND_EVENT:
            attrs['duration_minutes'] = None
        if kind != TripStop.KIND_TRAVEL:
            attrs['arrive_timezone'] = ''
        return attrs


class TripTodoSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none(), source='trip')
    day_id = serializers.PrimaryKeyRelatedField(
        queryset=TripDay.objects.none(), source='day', allow_null=True, required=False,
    )
    stop_id = serializers.PrimaryKeyRelatedField(
        queryset=TripStop.objects.none(), source='stop', allow_null=True, required=False,
    )

    class Meta:
        model = TripTodo
        fields = ['id', 'user', 'trip_id', 'day_id', 'stop_id', 'text', 'category', 'done', 'sort_order',
                  'created_at', 'modified_on']
        read_only_fields = ['sort_order']

    def validate_category(self, value):
        return ' '.join((value or '').split())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['day_id'], TripDay.objects.filter(trip__in=trips) if user else TripDay.objects.none())
        _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(trip__in=trips) if user else TripStop.objects.none())

    def validate(self, attrs):
        trip = attrs.get('trip') or getattr(self.instance, 'trip', None)
        day = attrs.get('day', getattr(self.instance, 'day', None))
        stop = attrs.get('stop', getattr(self.instance, 'stop', None))
        if stop:
            if trip and stop.trip_id != trip.id:
                raise serializers.ValidationError('Day or stop must belong to this trip.')
            day = stop.day
            attrs['day'] = day
        if day and trip and day.trip_id != trip.id:
            raise serializers.ValidationError('Day or stop must belong to this trip.')
        if not (attrs.get('text', getattr(self.instance, 'text', '')) or '').strip():
            raise serializers.ValidationError({'text': 'Enter a to-do.'})
        return attrs

    def create(self, validated_data):
        last = TripTodo.objects.filter(trip=validated_data['trip']).order_by('-sort_order').first()
        validated_data['sort_order'] = (last.sort_order + 1) if last else 0
        return super().create(validated_data)


class TripMediaSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
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
            trips = accessible_trips(user, write=True)
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.filter(owner=user))
            _set_pk_queryset(self.fields['trip_id'], trips)
            _set_pk_queryset(self.fields['day_id'], TripDay.objects.filter(trip__in=trips))
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(trip__in=trips))
        else:
            _set_pk_queryset(self.fields['asset_id'], UserMedia.objects.none())
            _set_pk_queryset(self.fields['trip_id'], Trip.objects.none())
            _set_pk_queryset(self.fields['day_id'], TripDay.objects.none())
            _set_pk_queryset(self.fields['stop_id'], TripStop.objects.none())


class TripLodgingSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
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
    attachments = TripStopAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TripLodging
        fields = [
            'id', 'user', 'trip', 'trip_id', 'name', 'address', 'phone', 'url',
            'confirmation', 'status', 'price', 'currency', 'person',
            'notes', 'check_in_time', 'check_out_time',
            'day_ids', 'assigned_day_ids', 'maps_url', 'day_count', 'attachments',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)

    def _assign_days(self, lodging, day_ids):
        days = list(TripDay.objects.filter(trip=lodging.trip, pk__in=day_ids))
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


def validate_contiguous_legs(trip, ordered_leg_ids, *, field='day_ids', target_leg_id=None):
    """Ensure every non-null leg_id in chronological day order forms one contiguous run."""
    seen_closed = set()
    prev = None
    for lid in ordered_leg_ids:
        if lid == prev:
            continue
        if prev is not None:
            seen_closed.add(prev)
        if lid is not None and lid in seen_closed:
            if target_leg_id is not None and lid == target_leg_id:
                raise serializers.ValidationError({
                    field: 'Days in a leg must be contiguous — no gaps between the first and last day.',
                })
            other = trip.legs.filter(pk=lid).first()
            name = other.name if other else 'another leg'
            raise serializers.ValidationError({
                field: f'This change would split leg “{name}” into non-contiguous days. Adjust “{name}” first or align with its edge.',
            })
        prev = lid


def sync_leg_order(trip):
    """Keep legs with days ordered chronologically by their earliest day; empty legs follow in order."""
    days = list(trip.days.order_by('date', 'id').values('leg_id', 'date'))
    first_date = {}
    for row in days:
        lid = row['leg_id']
        if lid is not None and lid not in first_date:
            first_date[lid] = row['date']
    legs = list(trip.legs.order_by('sort_order', 'id'))
    ordered = sorted(
        legs,
        key=lambda l: (0, first_date[l.pk], l.sort_order, l.pk)
        if l.pk in first_date
        else (1, None, l.sort_order, l.pk),
    )
    for i, l in enumerate(ordered):
        if l.sort_order != i:
            TripLeg.objects.filter(pk=l.pk).update(sort_order=i)


class TripLegSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    day_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    assigned_day_ids = serializers.PrimaryKeyRelatedField(
        source='days',
        many=True,
        read_only=True,
    )

    class Meta:
        model = TripLeg
        fields = [
            'id', 'user', 'trip', 'trip_id', 'name', 'location', 'timezone',
            'notes', 'sort_order', 'day_ids', 'assigned_day_ids',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)

    def validate_timezone(self, value):
        return _zone(value)

    def validate(self, attrs):
        day_ids = attrs.get('day_ids')
        trip = attrs.get('trip') or getattr(self.instance, 'trip', None)
        if day_ids is not None and trip is not None:
            all_days = list(TripDay.objects.filter(trip=trip).order_by('date', 'id'))
            valid_ids = {d.pk for d in all_days}
            day_id_set = set(day_ids)
            if not day_id_set.issubset(valid_ids):
                raise serializers.ValidationError({'day_ids': 'One or more days are not on this trip.'})
            target_id = self.instance.pk if self.instance else -1
            ordered_leg_ids = []
            for d in all_days:
                if d.pk in day_id_set:
                    ordered_leg_ids.append(target_id)
                elif self.instance and d.leg_id == self.instance.pk:
                    ordered_leg_ids.append(None)
                else:
                    ordered_leg_ids.append(d.leg_id)
            validate_contiguous_legs(trip, ordered_leg_ids, field='day_ids', target_leg_id=target_id)
        return attrs

    def _assign_days(self, leg, day_ids):
        days = list(TripDay.objects.filter(trip=leg.trip, pk__in=day_ids))
        if len(days) != len(set(day_ids)):
            raise serializers.ValidationError({'day_ids': 'One or more days are not on this trip.'})
        leg.days.exclude(pk__in=day_ids).update(leg=None)
        TripDay.objects.filter(pk__in=[d.pk for d in days]).update(leg=leg)
        sync_leg_order(leg.trip)

    def create(self, validated_data):
        day_ids = validated_data.pop('day_ids', None)
        if 'sort_order' not in validated_data and validated_data.get('trip'):
            last = validated_data['trip'].legs.order_by('-sort_order').first()
            validated_data['sort_order'] = (last.sort_order + 1) if last else 0
        leg = TripLeg.objects.create(**validated_data)
        if day_ids is not None:
            self._assign_days(leg, day_ids)
        return leg

    def update(self, instance, validated_data):
        day_ids = validated_data.pop('day_ids', None)
        leg = super().update(instance, validated_data)
        if day_ids is not None:
            self._assign_days(leg, day_ids)
        return leg


class TripLodgingSummarySerializer(serializers.ModelSerializer):
    maps_url = serializers.CharField(read_only=True)
    attachments = TripStopAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TripLodging
        fields = [
            'id', 'name', 'address', 'phone', 'url', 'confirmation',
            'status', 'price', 'currency', 'person',
            'notes', 'check_in_time', 'check_out_time', 'maps_url', 'attachments',
        ]


class TripDaySerializer(PreserveOwnerMixin, serializers.ModelSerializer):
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
    leg_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLeg.objects.none(),
        source='leg',
        allow_null=True,
        required=False,
    )
    stops = TripStopSerializer(many=True, read_only=True)
    media = TripMediaSerializer(many=True, read_only=True)
    stop_count = serializers.IntegerField(source='stops.count', read_only=True)

    class Meta:
        model = TripDay
        fields = [
            'id', 'user', 'trip', 'trip_id', 'date', 'title', 'notes', 'journal', 'timezone',
            'lodging', 'lodging_id', 'leg', 'leg_id',
            'sort_order', 'stops', 'media', 'stop_count',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip', 'lodging', 'leg']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        lodgings = TripLodging.objects.filter(trip__in=trips) if user else TripLodging.objects.none()
        legs = TripLeg.objects.filter(trip__in=trips) if user else TripLeg.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['lodging_id'], lodgings)
        _set_pk_queryset(self.fields['leg_id'], legs)

    def validate_timezone(self, value):
        return _zone(value)

    def validate(self, attrs):
        lodging = attrs.get('lodging')
        leg = attrs.get('leg', getattr(self.instance, 'leg', None))
        trip = attrs.get('trip') or getattr(self.instance, 'trip', None)
        if lodging and trip and lodging.trip_id != trip.id:
            raise serializers.ValidationError({'lodging_id': 'Lodging must belong to this trip.'})
        if leg and trip and leg.trip_id != trip.id:
            raise serializers.ValidationError({'leg_id': 'Leg must belong to this trip.'})
        if trip and ('leg' in attrs or 'date' in attrs):
            new_date = attrs.get('date', getattr(self.instance, 'date', None))
            new_leg_id = leg.pk if leg else None
            changed = (
                self.instance is None
                or new_date != self.instance.date
                or new_leg_id != self.instance.leg_id
            )
            if changed and new_date is not None:
                existing = list(trip.days.exclude(pk=getattr(self.instance, 'pk', None)).order_by('date', 'id'))
                rows = [(d.date, d.pk, d.leg_id) for d in existing]
                rows.append((new_date, getattr(self.instance, 'pk', None) or 10**12, new_leg_id))
                rows.sort(key=lambda r: (r[0], r[1]))
                validate_contiguous_legs(
                    trip,
                    [r[2] for r in rows],
                    field='leg_id',
                    target_leg_id=new_leg_id,
                )
        return attrs

    def create(self, validated_data):
        day = super().create(validated_data)
        sync_leg_order(day.trip)
        return day

    def update(self, instance, validated_data):
        day = super().update(instance, validated_data)
        if 'leg' in validated_data or 'date' in validated_data:
            sync_leg_order(day.trip)
        return day


class TripShareSerializer(serializers.ModelSerializer):
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    user_label = serializers.SerializerMethodField()
    accepted = serializers.SerializerMethodField()

    class Meta:
        model = TripShare
        fields = [
            'id', 'trip', 'trip_id', 'email', 'role',
            'user', 'user_label', 'accepted',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['trip', 'user', 'created_at', 'modified_on']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        _set_pk_queryset(self.fields['trip_id'], owned_trips(user) if user else Trip.objects.none())

    def get_user_label(self, obj):
        if obj.user_id:
            return user_display_label(obj.user)
        return obj.email

    def get_accepted(self, obj):
        return bool(obj.user_id)

    def validate_email(self, value):
        return (value or '').strip().lower()

    def validate(self, attrs):
        trip = attrs.get('trip') or getattr(self.instance, 'trip', None)
        email = attrs.get('email', getattr(self.instance, 'email', '')).strip().lower()
        if trip is None:
            raise serializers.ValidationError({'trip_id': 'Trip is required.'})
        if not email:
            raise serializers.ValidationError({'email': 'Email is required.'})
        owner_email = (getattr(trip.user, 'email', '') or '').strip().lower()
        if owner_email and email == owner_email:
            raise serializers.ValidationError({'email': 'The trip owner already has full access.'})
        if self.instance is None and TripShare.objects.filter(trip=trip, email__iexact=email).exists():
            raise serializers.ValidationError({'email': 'This person is already shared on this trip.'})
        attrs['email'] = email
        return attrs

    def create(self, validated_data):
        User = get_user_model()
        email = validated_data['email']
        matched_user = User.objects.filter(email__iexact=email).first()
        validated_data['user'] = matched_user
        return super().create(validated_data)


class TripCommentSerializer(serializers.ModelSerializer):
    trip_id = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.none(),
        source='trip',
        required=False,
    )
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=TripComment.objects.none(),
        source='parent',
        allow_null=True,
        required=False,
    )
    leg_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLeg.objects.none(),
        source='leg',
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
    lodging_id = serializers.PrimaryKeyRelatedField(
        queryset=TripLodging.objects.none(),
        source='lodging',
        allow_null=True,
        required=False,
    )
    target_type = serializers.CharField(read_only=True)
    author_label = serializers.SerializerMethodField()
    author_email = serializers.SerializerMethodField()
    resolved_by_label = serializers.SerializerMethodField()

    class Meta:
        model = TripComment
        fields = [
            'id', 'trip', 'trip_id', 'parent', 'parent_id',
            'leg', 'leg_id', 'day', 'day_id', 'stop', 'stop_id', 'lodging', 'lodging_id',
            'target_type', 'body',
            'author', 'author_label', 'author_email',
            'resolved', 'resolved_at', 'resolved_by', 'resolved_by_label',
            'created_at', 'modified_on',
        ]
        read_only_fields = [
            'trip', 'parent', 'leg', 'day', 'stop', 'lodging',
            'author', 'resolved_at', 'resolved_by', 'created_at', 'modified_on',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=False) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['parent_id'], TripComment.objects.filter(trip__in=trips) if user else TripComment.objects.none())
        _set_pk_queryset(self.fields['leg_id'], TripLeg.objects.filter(trip__in=trips) if user else TripLeg.objects.none())
        _set_pk_queryset(self.fields['day_id'], TripDay.objects.filter(trip__in=trips) if user else TripDay.objects.none())
        _set_pk_queryset(self.fields['stop_id'], TripStop.objects.filter(trip__in=trips) if user else TripStop.objects.none())
        _set_pk_queryset(self.fields['lodging_id'], TripLodging.objects.filter(trip__in=trips) if user else TripLodging.objects.none())

    def get_author_label(self, obj):
        return user_display_label(obj.author)

    def get_author_email(self, obj):
        return getattr(obj.author, 'email', '') or ''

    def get_resolved_by_label(self, obj):
        return user_display_label(obj.resolved_by) if obj.resolved_by_id else ''

    def validate_body(self, value):
        if not (value or '').strip():
            raise serializers.ValidationError('Enter a comment.')
        return value.strip()

    def validate(self, attrs):
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        if parent is not None:
            # Keep reply threads cleanly one level deep by attaching to the root comment.
            root = parent.parent if parent.parent_id else parent
            attrs['parent'] = root
            attrs['trip'] = root.trip
            attrs['leg'] = root.leg
            attrs['day'] = root.day
            attrs['stop'] = root.stop
            attrs['lodging'] = root.lodging
            return attrs

        leg = attrs.get('leg', getattr(self.instance, 'leg', None))
        day = attrs.get('day', getattr(self.instance, 'day', None))
        stop = attrs.get('stop', getattr(self.instance, 'stop', None))
        lodging = attrs.get('lodging', getattr(self.instance, 'lodging', None))
        targets = [t for t in (leg, day, stop, lodging) if t is not None]
        if len(targets) > 1:
            raise serializers.ValidationError('Attach a comment to at most one leg, day, stop, or lodging.')

        trip = (
            attrs.get('trip')
            or (leg.trip if leg else None)
            or (day.trip if day else None)
            or (stop.trip if stop else None)
            or (lodging.trip if lodging else None)
            or getattr(self.instance, 'trip', None)
        )
        if trip is None:
            raise serializers.ValidationError({'trip_id': 'Trip is required.'})
        for field_name, obj in (('leg_id', leg), ('day_id', day), ('stop_id', stop), ('lodging_id', lodging)):
            if obj is not None and obj.trip_id != trip.id:
                raise serializers.ValidationError({field_name: 'Target must belong to this trip.'})
        attrs['trip'] = trip
        return attrs


class TripSerializer(PreserveOwnerMixin, serializers.ModelSerializer):
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
    legs = TripLegSerializer(many=True, read_only=True)
    ideas = serializers.SerializerMethodField()
    lodgings = TripLodgingSerializer(many=True, read_only=True)
    todos = TripTodoSerializer(many=True, read_only=True)
    comments = TripCommentSerializer(many=True, read_only=True)
    shares = serializers.SerializerMethodField()
    day_count = serializers.IntegerField(source='days.count', read_only=True)
    my_role = serializers.SerializerMethodField()
    owner_label = serializers.SerializerMethodField()
    share_count = serializers.SerializerMethodField()
    open_comment_count = serializers.SerializerMethodField()
    public_enabled = serializers.SerializerMethodField()
    share_token = serializers.SerializerMethodField()
    public_path = serializers.SerializerMethodField()
    generate_days = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Trip
        fields = [
            'id', 'user', 'title', 'description', 'notes', 'start_date', 'end_date', 'timezone',
            'packing_list', 'packing_list_id',
            'gallery', 'gallery_id',
            'my_role', 'owner_label', 'share_count', 'open_comment_count',
            'public_enabled', 'share_token', 'public_path', 'notify_on_comments', 'shares',
            'days', 'legs', 'ideas', 'lodgings', 'todos', 'comments', 'day_count', 'generate_days',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['packing_list', 'gallery']

    def get_my_role(self, obj):
        user = _request_user(self)
        return trip_role(obj, user) or ROLE_OWNER

    def get_owner_label(self, obj):
        return user_display_label(obj.user)

    def get_share_count(self, obj):
        cache = getattr(obj, '_prefetched_objects_cache', {}).get('shares')
        if cache is not None:
            return len(cache)
        return obj.shares.count()

    def get_open_comment_count(self, obj):
        cache = getattr(obj, '_prefetched_objects_cache', {}).get('comments')
        if cache is not None:
            return sum(1 for c in cache if c.parent_id is None and not c.resolved)
        return obj.comments.filter(parent__isnull=True, resolved=False).count()

    def _is_owner(self, obj):
        user = _request_user(self)
        return is_trip_owner(obj, user)

    def get_public_enabled(self, obj):
        return bool(obj.public_enabled and obj.share_token) if self._is_owner(obj) else False

    def get_share_token(self, obj):
        return (obj.share_token or '') if self._is_owner(obj) else ''

    def get_public_path(self, obj):
        if self._is_owner(obj) and obj.public_enabled and obj.share_token:
            return f'/app/trips/share/{obj.share_token}'
        return ''

    def get_shares(self, obj):
        if not self._is_owner(obj):
            return []
        return TripShareSerializer(obj.shares.all(), many=True, context=self.context).data

    def get_ideas(self, obj):
        items = getattr(obj, 'unscheduled_ideas', None)
        if items is None:
            items = obj.stops.filter(day__isnull=True).order_by('sort_order', 'id')
        return TripStopSerializer(items, many=True, context=self.context).data

    def validate_timezone(self, value):
        return _zone(value)

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})
        if attrs.get('generate_days') and start and end and (end - start).days >= 90:
            raise serializers.ValidationError({'end_date': 'Date range cannot exceed 90 days when generating days.'})
        if self.instance is not None and 'notify_on_comments' in attrs:
            if attrs['notify_on_comments'] != self.instance.notify_on_comments and not self._is_owner(self.instance):
                raise serializers.ValidationError(
                    {'notify_on_comments': 'Only the trip owner can change comment email notifications.'}
                )
        return attrs

    def create(self, validated_data):
        from datetime import timedelta

        generate = validated_data.pop('generate_days', False)
        trip = super().create(validated_data)
        if generate and trip.start_date and trip.end_date:
            cur = trip.start_date
            to_create = []
            while cur <= trip.end_date:
                to_create.append(TripDay(user=trip.user, trip=trip, date=cur))
                cur += timedelta(days=1)
            TripDay.objects.bulk_create(to_create)
        return trip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user:
            _set_pk_queryset(self.fields['packing_list_id'], VacList.objects.filter(user=user))
            _set_pk_queryset(self.fields['gallery_id'], Gallery.objects.filter(owner=user))
        else:
            _set_pk_queryset(self.fields['packing_list_id'], VacList.objects.none())
            _set_pk_queryset(self.fields['gallery_id'], Gallery.objects.none())


class PublicTripAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = TripStopAttachment
        fields = [
            'id', 'kind', 'title', 'url', 'osm_url', 'address', 'lat', 'lng',
            'file_url', 'thumbnail_url', 'sort_order',
        ]

    def get_file_url(self, obj):
        return obj.asset.url if obj.asset_id else obj.url

    def get_thumbnail_url(self, obj):
        return obj.asset.thumbnail_url if obj.asset_id else ''


def _public_attachments(obj):
    items = [a for a in obj.attachments.all() if a.kind != TripStopAttachment.KIND_DOCUMENT]
    return PublicTripAttachmentSerializer(items, many=True).data


class PublicTripLodgingSerializer(serializers.ModelSerializer):
    assigned_day_ids = serializers.PrimaryKeyRelatedField(source='days', many=True, read_only=True)
    maps_url = serializers.CharField(read_only=True)
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = TripLodging
        fields = [
            'id', 'name', 'address', 'phone', 'url', 'notes',
            'check_in_time', 'check_out_time', 'assigned_day_ids', 'maps_url', 'attachments',
        ]

    def get_attachments(self, obj):
        return _public_attachments(obj)


class PublicTripStopSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = TripStop
        fields = [
            'id', 'day', 'leg', 'kind', 'travel_mode', 'text', 'description',
            'loc', 'arrive_loc', 'cat', 'status', 'start_time', 'duration_minutes',
            'timezone', 'arrive_timezone', 'sort_order', 'attachments',
        ]

    def get_attachments(self, obj):
        return _public_attachments(obj)


class PublicTripDaySerializer(serializers.ModelSerializer):
    lodging = PublicTripLodgingSerializer(read_only=True)
    stops = PublicTripStopSerializer(many=True, read_only=True)
    media = TripMediaSerializer(many=True, read_only=True)

    class Meta:
        model = TripDay
        fields = [
            'id', 'date', 'title', 'notes', 'journal', 'timezone',
            'lodging', 'leg', 'sort_order', 'stops', 'media',
        ]


class PublicTripLegSerializer(serializers.ModelSerializer):
    assigned_day_ids = serializers.PrimaryKeyRelatedField(source='days', many=True, read_only=True)

    class Meta:
        model = TripLeg
        fields = ['id', 'name', 'location', 'timezone', 'notes', 'sort_order', 'assigned_day_ids']


class PublicTripSerializer(serializers.ModelSerializer):
    owner_label = serializers.SerializerMethodField()
    days = PublicTripDaySerializer(many=True, read_only=True)
    legs = PublicTripLegSerializer(many=True, read_only=True)
    ideas = serializers.SerializerMethodField()
    lodgings = PublicTripLodgingSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'title', 'description', 'notes', 'start_date', 'end_date', 'timezone',
            'owner_label', 'days', 'legs', 'ideas', 'lodgings',
        ]

    def get_owner_label(self, obj):
        return user_display_label(obj.user)

    def get_ideas(self, obj):
        items = getattr(obj, 'unscheduled_ideas', None)
        if items is None:
            items = obj.stops.filter(day__isnull=True).order_by('sort_order', 'id')
        return PublicTripStopSerializer(items, many=True).data


class TripSuggestionSerializer(serializers.ModelSerializer):
    draft = serializers.SerializerMethodField()
    maps_url = serializers.SerializerMethodField()

    class Meta:
        model = TripSuggestion
        fields = ['id', 'kind', 'data', 'draft', 'maps_url', 'status', 'stop_id', 'lodging_id', 'created_at']
        read_only_fields = fields

    def get_draft(self, obj):
        from .ai import draft_fields

        return draft_fields(obj)

    def get_maps_url(self, obj):
        from .ai import map_query

        return google_maps_url(map_query(obj.data))


class TripSuggestionBatchSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    trip_id = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none(), source='trip')
    day_id = serializers.PrimaryKeyRelatedField(
        queryset=TripDay.objects.none(), source='day', allow_null=True, required=False,
    )
    prompt = serializers.CharField(max_length=2000)
    suggestions = TripSuggestionSerializer(many=True, read_only=True)

    class Meta:
        model = TripSuggestionBatch
        fields = ['id', 'user', 'trip_id', 'day_id', 'prompt', 'status', 'error', 'suggestions', 'created_at']
        read_only_fields = ['status', 'error']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        trips = accessible_trips(user, write=True) if user else Trip.objects.none()
        _set_pk_queryset(self.fields['trip_id'], trips)
        _set_pk_queryset(self.fields['day_id'], TripDay.objects.filter(trip__in=trips) if user else TripDay.objects.none())

    def validate(self, attrs):
        day = attrs.get('day')
        if day and day.trip_id != attrs['trip'].id:
            raise serializers.ValidationError({'day_id': 'Day must belong to this trip.'})
        if not attrs['prompt'].strip():
            raise serializers.ValidationError({'prompt': 'Ask for something.'})
        return attrs


class TripListSerializer(TripSerializer):
    class Meta(TripSerializer.Meta):
        fields = [
            'id', 'user', 'title', 'start_date', 'end_date',
            'packing_list', 'packing_list_id',
            'gallery', 'gallery_id',
            'my_role', 'owner_label', 'share_count', 'open_comment_count', 'public_enabled',
            'day_count',
            'created_at', 'modified_on',
        ]
