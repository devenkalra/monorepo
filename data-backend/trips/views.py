from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Trip, TripDay, TripLodging, TripStop, TripMedia, TripStopAttachment
from .seed_death_valley import create_death_valley_trip
from .serializers import (
    TripDaySerializer,
    TripListSerializer,
    TripLodgingSerializer,
    TripMediaSerializer,
    TripSerializer,
    TripStopAttachmentSerializer,
    TripStopSerializer,
)


def _renumber_days(trip):
    for i, day in enumerate(trip.days.order_by('date', 'id')):
        if day.sort_order != i:
            day.sort_order = i
            day.save(update_fields=['sort_order'])


class UserScopedMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()
        return qs.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TripViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return TripListSerializer
        return TripSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            return qs.prefetch_related(
                Prefetch(
                    'days',
                    queryset=TripDay.objects.select_related('lodging').prefetch_related(
                        Prefetch(
                            'lodging__attachments',
                            queryset=TripStopAttachment.objects.select_related('asset'),
                        )
                    ).order_by('date', 'sort_order', 'id'),
                ),
                Prefetch(
                    'lodgings',
                    queryset=TripLodging.objects.prefetch_related(
                        Prefetch(
                            'attachments',
                            queryset=TripStopAttachment.objects.select_related('asset'),
                        )
                    ),
                ),
                Prefetch(
                    'days__stops',
                    queryset=TripStop.objects.order_by('sort_order', 'id').prefetch_related(
                        Prefetch(
                            'attachments',
                            queryset=TripStopAttachment.objects.select_related('asset'),
                        )
                    ),
                ),
                'days__media__asset',
                'media__asset',
            )
        return qs

    @action(detail=False, methods=['post'], url_path='seed-death-valley')
    def seed_death_valley(self, request):
        trip, created = create_death_valley_trip(request.user)
        data = TripSerializer(trip, context={'request': request}).data
        data['created'] = created
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TripLodgingViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = TripLodging.objects.select_related('trip').prefetch_related('days', 'attachments__asset')
    serializer_class = TripLodgingSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        return qs


class TripDayViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = TripDay.objects.select_related('trip', 'lodging').prefetch_related(
        'stops',
        'media__asset',
        'lodging__attachments__asset',
    )
    serializer_class = TripDaySerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        return qs

    def perform_create(self, serializer):
        day = serializer.save(user=self.request.user)
        _renumber_days(day.trip)
        day.trip.sync_dates_from_days()

    def perform_update(self, serializer):
        day = serializer.save()
        _renumber_days(day.trip)
        day.trip.sync_dates_from_days()

    def perform_destroy(self, instance):
        trip = instance.trip
        super().perform_destroy(instance)
        _renumber_days(trip)
        trip.sync_dates_from_days()


def _next_stop_order(day, exclude_pk=None):
    qs = day.stops.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    max_order = qs.order_by('-sort_order').values_list('sort_order', flat=True).first()
    return 0 if max_order is None else max_order + 1


class TripStopViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = TripStop.objects.select_related('day')
    serializer_class = TripStopSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        day_id = self.request.query_params.get('day')
        if day_id:
            qs = qs.filter(day_id=day_id)
        return qs

    def perform_create(self, serializer):
        stop = serializer.save(user=self.request.user)
        if 'sort_order' not in serializer.validated_data:
            stop.sort_order = _next_stop_order(stop.day, exclude_pk=stop.pk)
            stop.save(update_fields=['sort_order'])

    def perform_update(self, serializer):
        old_day_id = serializer.instance.day_id
        stop = serializer.save()
        if stop.day_id != old_day_id:
            stop.sort_order = _next_stop_order(stop.day, exclude_pk=stop.pk)
            stop.save(update_fields=['sort_order'])

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        stop = self.get_object()
        direction = request.data.get('direction')
        if direction not in ('up', 'down'):
            return Response({'direction': 'Must be "up" or "down".'}, status=status.HTTP_400_BAD_REQUEST)
        siblings = list(stop.day.stops.order_by('sort_order', 'id'))
        idx = next(i for i, row in enumerate(siblings) if row.pk == stop.pk)
        swap = idx - 1 if direction == 'up' else idx + 1
        if 0 <= swap < len(siblings):
            siblings[idx], siblings[swap] = siblings[swap], siblings[idx]
            for i, row in enumerate(siblings):
                if row.sort_order != i:
                    row.sort_order = i
                    row.save(update_fields=['sort_order'])
        return Response(self.get_serializer(stop).data)


class TripMediaViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = TripMedia.objects.select_related('asset', 'trip', 'day', 'stop')
    serializer_class = TripMediaSerializer
    pagination_class = None


class TripStopAttachmentViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = TripStopAttachment.objects.select_related('stop', 'lodging', 'asset')
    serializer_class = TripStopAttachmentSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        stop_id = self.request.query_params.get('stop')
        lodging_id = self.request.query_params.get('lodging')
        if stop_id:
            qs = qs.filter(stop_id=stop_id)
        if lodging_id:
            qs = qs.filter(lodging_id=lodging_id)
        return qs
