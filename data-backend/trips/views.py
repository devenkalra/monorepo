from datetime import date, timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from productions.llm import llm_available

from . import ai as trip_ai
from . import report as trip_report
from . import transfer
from .access import (
    accessible_trips,
    can_edit_trip,
    can_view_trip,
    is_trip_owner,
    owned_trips,
)
from .models import (
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
from .seed_death_valley import create_death_valley_trip
from .serializers import (
    PublicTripSerializer,
    TripCommentSerializer,
    TripDaySerializer,
    TripLegSerializer,
    TripListSerializer,
    TripLodgingSerializer,
    TripMediaSerializer,
    TripSerializer,
    TripShareSerializer,
    TripStopAttachmentSerializer,
    TripStopSerializer,
    TripSuggestionBatchSerializer,
    TripSuggestionSerializer,
    TripTodoSerializer,
    sync_leg_order,
    validate_contiguous_legs,
)
from .tasks import generate_suggestions


def _renumber_days(trip):
    for i, day in enumerate(trip.days.order_by('date', 'id')):
        if day.sort_order != i:
            day.sort_order = i
            day.save(update_fields=['sort_order'])


def _reassign_day_dates(pairs):
    """Collision-free update of [(TripDay, target_date), ...] inside an atomic block."""
    changed = [(day, target) for day, target in pairs if day.date != target]
    if not changed:
        return
    temp_base = date(3000, 1, 1)
    for i, (day, _) in enumerate(changed):
        TripDay.objects.filter(pk=day.pk).update(date=temp_base + timedelta(days=i))
    for day, target in changed:
        TripDay.objects.filter(pk=day.pk).update(date=target)
        day.date = target


def _trip_detail_prefetches():
    return [
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
        Prefetch(
            'stops',
            queryset=TripStop.objects.filter(day__isnull=True).select_related('leg').order_by('sort_order', 'id').prefetch_related(
                Prefetch(
                    'attachments',
                    queryset=TripStopAttachment.objects.select_related('asset'),
                )
            ),
            to_attr='unscheduled_ideas',
        ),
        'legs__days',
        'days__media__asset',
        'media__asset',
        'todos',
        Prefetch('shares', queryset=TripShare.objects.select_related('user')),
        Prefetch('comments', queryset=TripComment.objects.select_related('author', 'resolved_by')),
    ]


class TripAccessMixin:
    """Scope querysets to trips accessible by the current user and enforce editor/owner permissions."""

    trip_lookup = 'trip'

    def _accessible_trips(self, *, write=False):
        return accessible_trips(getattr(self.request, 'user', None), write=write)

    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()
        trips = self._accessible_trips(write=False)
        if self.trip_lookup is None:
            return qs.filter(pk__in=trips)
        return qs.filter(**{f'{self.trip_lookup}__in': trips})

    def _resolve_trip(self, obj):
        if isinstance(obj, Trip):
            return obj
        if hasattr(obj, 'trip') and obj.trip is not None:
            return obj.trip
        if hasattr(obj, 'day') and obj.day is not None:
            return obj.day.trip
        if hasattr(obj, 'stop') and obj.stop is not None:
            return obj.stop.trip
        if hasattr(obj, 'lodging') and obj.lodging is not None:
            return obj.lodging.trip
        if hasattr(obj, 'batch') and obj.batch is not None:
            return obj.batch.trip
        return None

    def _resolve_trip_from_validated(self, validated_data):
        if validated_data.get('trip'):
            return validated_data['trip']
        for key in ('day', 'leg', 'stop', 'lodging', 'batch'):
            obj = validated_data.get(key)
            if obj is not None:
                return self._resolve_trip(obj)
        return None

    def _require_edit(self, trip):
        if not trip or not can_edit_trip(trip, self.request.user):
            raise PermissionDenied('You have view-only access to this trip.')

    def _require_owner(self, trip):
        if not trip or not is_trip_owner(trip, self.request.user):
            raise PermissionDenied('Only the trip owner can perform this action.')

    def perform_create(self, serializer):
        trip = self._resolve_trip_from_validated(serializer.validated_data)
        self._require_edit(trip)
        serializer.save(user=trip.user)

    def perform_update(self, serializer):
        trip = self._resolve_trip(serializer.instance)
        self._require_edit(trip)
        serializer.save()

    def perform_destroy(self, instance):
        trip = self._resolve_trip(instance)
        self._require_edit(trip)
        instance.delete()


class TripViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = Trip.objects.select_related('user')
    pagination_class = None
    trip_lookup = None

    def get_serializer_class(self):
        if self.action == 'list':
            return TripListSerializer
        return TripSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.select_related('user').prefetch_related('shares', 'comments')
        if self.action == 'retrieve':
            return qs.select_related('user').prefetch_related(*_trip_detail_prefetches())
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        self._require_edit(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_owner(instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='public-link')
    def public_link(self, request, pk=None):
        """Owner-only: enable/disable or regenerate the obfuscated public read-only link."""
        trip = self.get_object()
        self._require_owner(trip)
        enabled = request.data.get('enabled')
        regenerate = bool(request.data.get('regenerate', False))
        if regenerate:
            trip.ensure_share_token(rotate=True)
        if enabled is not None:
            trip.public_enabled = bool(enabled)
            if trip.public_enabled:
                trip.ensure_share_token()
        elif not regenerate and not trip.share_token:
            trip.ensure_share_token()
        trip.save(update_fields=['public_enabled', 'share_token', 'modified_on'])
        return Response({
            'public_enabled': bool(trip.public_enabled and trip.share_token),
            'share_token': trip.share_token or '',
            'public_path': f'/app/trips/share/{trip.share_token}' if (trip.public_enabled and trip.share_token) else '',
        })

    @action(detail=True, methods=['post'], url_path='leave')
    def leave(self, request, pk=None):
        """Allow a non-owner collaborator to remove themselves from a shared trip."""
        trip = self.get_object()
        if is_trip_owner(trip, request.user):
            return Response({'detail': 'Trip owners cannot leave their own trip.'}, status=status.HTTP_400_BAD_REQUEST)
        email = (getattr(request.user, 'email', '') or '').strip().lower()
        q = Q(user=request.user)
        if email:
            q |= Q(email__iexact=email)
        TripShare.objects.filter(trip=trip).filter(q).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='seed-death-valley')
    def seed_death_valley(self, request):
        trip, created = create_death_valley_trip(request.user)
        data = TripSerializer(trip, context={'request': request}).data
        data['created'] = created
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        trip = self.get_object()
        include_sharing = is_trip_owner(trip, request.user)
        response = HttpResponse(
            transfer.export_zip([trip], include_sharing=include_sharing),
            content_type='application/zip',
        )
        response['Content-Disposition'] = f'attachment; filename="{transfer.export_filename([trip])}"'
        return response

    @action(detail=False, methods=['get'], url_path='export-all')
    def export_all(self, request):
        trips = list(Trip.objects.filter(user=request.user).select_related('packing_list', 'gallery'))
        if not trips:
            return Response({'detail': 'You have no owned trips to export.'}, status=status.HTTP_400_BAD_REQUEST)
        response = HttpResponse(
            transfer.export_zip(trips, include_sharing=True),
            content_type='application/zip',
        )
        response['Content-Disposition'] = f'attachment; filename="{transfer.export_filename(trips)}"'
        return response

    @action(detail=False, methods=['post'], url_path='import', parser_classes=[MultiPartParser])
    def import_trips(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'Choose a trip export file.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload, load_file = transfer.read_bundle(upload)
            trips, counts = transfer.import_payload(request.user, payload, load_file)
        except transfer.TransferError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (KeyError, TypeError, ValueError) as exc:
            return Response({'detail': f'Export file is malformed: {exc}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {'trips': TripListSerializer(trips, many=True, context={'request': request}).data, 'counts': counts},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        """?type=full|summary|expenses; full also takes ?sections=overview,days,todos,expenses."""
        trip = self.get_object()
        hide_done = request.query_params.get('hide_done') in ('1', 'true')
        kind = request.query_params.get('type') or 'full'
        if kind not in trip_report.KINDS:
            return Response({'detail': f'Unknown report type "{kind}".'}, status=status.HTTP_400_BAD_REQUEST)
        sections = trip_report.KINDS[kind]
        if kind == 'full' and 'sections' in request.query_params:
            sections = [s for s in request.query_params['sections'].split(',') if s]
            unknown = set(sections) - set(trip_report.SECTIONS)
            if unknown:
                return Response({'detail': f'Unknown sections: {", ".join(sorted(unknown))}.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not sections:
                return Response({'detail': 'Pick at least one section.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'markdown': trip_report.build(trip, hide_done=hide_done, sections=sections),
            'filename': trip_report.filename(trip, kind),
        })

    @action(detail=True, methods=['post'], url_path='bulk-days')
    def bulk_days(self, request, pk=None):
        """Update/create day outlines (date, title, notes) for high-level planning.

        Existing days omitted from the payload are left alone (use Delete day to remove).
        """
        trip = self.get_object()
        self._require_edit(trip)
        items = request.data.get('items')
        if not isinstance(items, list):
            return Response({'items': 'Expected a list of rows.'}, status=status.HTTP_400_BAD_REQUEST)
        if not items:
            return Response({'items': 'Add at least one day.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = {day.id: day for day in trip.days.all()}
        seen_dates = set()
        with transaction.atomic():
            for index, raw in enumerate(items):
                if not isinstance(raw, dict):
                    return Response(
                        {'items': f'Row {index + 1} must be an object.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                date = (raw.get('date') or '').strip()
                if not date:
                    return Response(
                        {'items': f'Row {index + 1} needs a date.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if date in seen_dates:
                    return Response(
                        {'items': f'Duplicate date {date} in the table.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                seen_dates.add(date)
                payload = {
                    'trip_id': trip.id,
                    'date': date,
                    'title': (raw.get('title') or '').strip(),
                    'notes': raw.get('notes') if raw.get('notes') is not None else '',
                }
                day_id = raw.get('id')
                instance = existing.get(day_id) if day_id else None
                if instance is None:
                    # Creating a day on a date that already exists should update that day.
                    instance = next((d for d in existing.values() if str(d.date) == date), None)
                if instance is None:
                    serializer = TripDaySerializer(data=payload, context={'request': request})
                else:
                    serializer = TripDaySerializer(
                        instance,
                        data=payload,
                        partial=True,
                        context={'request': request},
                    )
                serializer.is_valid(raise_exception=True)
                serializer.save(user=trip.user, trip=trip)

        _renumber_days(trip)
        trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    def _trip_response(self, request, trip):
        self.action = 'retrieve'
        fresh = self.get_queryset().filter(pk=trip.pk).first() or trip
        return Response(TripSerializer(fresh, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='shift-dates')
    def shift_dates(self, request, pk=None):
        """Shift every day in the trip by ±N days, or to a new start_date."""
        trip = self.get_object()
        self._require_edit(trip)
        days = list(trip.days.order_by('date', 'id'))
        if not days:
            return Response({'detail': 'Trip has no days to shift.'}, status=status.HTTP_400_BAD_REQUEST)
        delta_days = request.data.get('days')
        new_start = request.data.get('start_date')
        if new_start:
            parsed = parse_date(str(new_start))
            if not parsed:
                return Response({'start_date': 'Invalid date.'}, status=status.HTTP_400_BAD_REQUEST)
            delta = (parsed - days[0].date).days
        else:
            try:
                delta = int(delta_days)
            except (TypeError, ValueError):
                return Response({'days': 'Provide an integer number of days or a start_date.'}, status=status.HTTP_400_BAD_REQUEST)
        if delta == 0:
            return self._trip_response(request, trip)
        if abs(delta) > 3650:
            return Response({'days': 'Shift cannot exceed 10 years.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            _reassign_day_dates([(d, d.date + timedelta(days=delta)) for d in days])
            _renumber_days(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    @action(detail=True, methods=['post'], url_path='insert-day')
    def insert_day(self, request, pk=None):
        """Insert a new day at `date`; when `ripple` is true, push days >= `date` forward by +1 day."""
        trip = self.get_object()
        self._require_edit(trip)
        target = parse_date(str(request.data.get('date') or ''))
        if not target:
            return Response({'date': 'Valid date is required.'}, status=status.HTTP_400_BAD_REQUEST)
        ripple = bool(request.data.get('ripple', True))
        title = (request.data.get('title') or '').strip()
        leg_id = request.data.get('leg_id')
        leg = None
        if leg_id is not None and leg_id != '':
            leg = trip.legs.filter(pk=leg_id).first()
            if not leg:
                return Response({'leg_id': 'Leg does not belong to this trip.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            days = list(trip.days.order_by('date', 'id'))
            existing_at = next((d for d in days if d.date == target), None)
            if existing_at and not ripple:
                return Response({'date': 'A day already exists on this date.'}, status=status.HTTP_400_BAD_REQUEST)
            post_dates = [
                (d.date + timedelta(days=1) if (ripple and d.date >= target) else d.date, d.pk, d.leg_id)
                for d in days
            ]
            prev_row = next((r for r in reversed(post_dates) if r[0] < target), None)
            next_row = next((r for r in post_dates if r[0] > target), None)
            if leg is None:
                if existing_at and existing_at.leg_id:
                    leg = existing_at.leg
                elif prev_row and next_row and prev_row[2] and prev_row[2] == next_row[2]:
                    leg = trip.legs.filter(pk=prev_row[2]).first()
            projected = sorted(
                post_dates + [(target, 10**12, leg.pk if leg else None)],
                key=lambda r: (r[0], r[1]),
            )
            validate_contiguous_legs(
                trip,
                [r[2] for r in projected],
                field='leg_id',
                target_leg_id=leg.pk if leg else None,
            )
            if ripple:
                to_shift = [(d, d.date + timedelta(days=1)) for d in days if d.date >= target]
                _reassign_day_dates(to_shift)
            TripDay.objects.create(user=trip.user, trip=trip, date=target, title=title, leg=leg)
            _renumber_days(trip)
            sync_leg_order(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    @action(detail=True, methods=['post'], url_path='remove-day')
    def remove_day(self, request, pk=None):
        """Delete a day; when `ripple` is true, pull all later days backward by -1 day."""
        trip = self.get_object()
        self._require_edit(trip)
        day = trip.days.filter(pk=request.data.get('day_id')).first()
        if not day:
            return Response({'day_id': 'Day not found on this trip.'}, status=status.HTTP_400_BAD_REQUEST)
        ripple = bool(request.data.get('ripple', True))
        removed_date = day.date
        with transaction.atomic():
            day.delete()
            if ripple:
                later = list(trip.days.filter(date__gt=removed_date).order_by('date', 'id'))
                _reassign_day_dates([(d, d.date - timedelta(days=1)) for d in later])
            _renumber_days(trip)
            sync_leg_order(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    @action(detail=True, methods=['post'], url_path='swap-days')
    def swap_days(self, request, pk=None):
        """Swap two days' dates (and leg slots) so each day's full itinerary moves to the other's date."""
        trip = self.get_object()
        self._require_edit(trip)
        day_a = trip.days.filter(pk=request.data.get('day_a_id')).first()
        day_b = trip.days.filter(pk=request.data.get('day_b_id')).first()
        if not day_a or not day_b or day_a.pk == day_b.pk:
            return Response({'detail': 'Choose two different days on this trip.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            date_a, date_b = day_a.date, day_b.date
            leg_a, leg_b = day_a.leg_id, day_b.leg_id
            _reassign_day_dates([(day_a, date_b), (day_b, date_a)])
            TripDay.objects.filter(pk=day_a.pk).update(leg_id=leg_b)
            TripDay.objects.filter(pk=day_b.pk).update(leg_id=leg_a)
            _renumber_days(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    @action(detail=True, methods=['post'], url_path='move-day')
    def move_day(self, request, pk=None):
        """Move a day to `target_date` (mode='shift' ripples intervening days; mode='empty' requires an open date)."""
        trip = self.get_object()
        self._require_edit(trip)
        day = trip.days.filter(pk=request.data.get('day_id')).first()
        target = parse_date(str(request.data.get('target_date') or ''))
        if not day:
            return Response({'day_id': 'Day not found on this trip.'}, status=status.HTTP_400_BAD_REQUEST)
        if not target:
            return Response({'target_date': 'Valid target date is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if day.date == target:
            return self._trip_response(request, trip)
        mode = request.data.get('mode') or 'shift'
        with transaction.atomic():
            days = list(trip.days.order_by('date', 'id'))
            occupant = next((d for d in days if d.date == target), None)
            if mode == 'empty':
                if occupant:
                    return Response({'target_date': 'Another day already exists on that date.'}, status=status.HTTP_400_BAD_REQUEST)
                _reassign_day_dates([(day, target)])
                # Preserve contiguity if moving to an open date jumped past another leg
                after_days = list(trip.days.order_by('date', 'id'))
                idx = next((i for i, d in enumerate(after_days) if d.pk == day.pk), -1)
                prev_leg = after_days[idx - 1].leg_id if idx > 0 else None
                next_leg = after_days[idx + 1].leg_id if 0 <= idx < len(after_days) - 1 else None
                if prev_leg and prev_leg == next_leg and day.leg_id != prev_leg:
                    TripDay.objects.filter(pk=day.pk).update(leg_id=prev_leg)
                elif day.leg_id is not None:
                    try:
                        validate_contiguous_legs(trip, [d.leg_id for d in after_days], target_leg_id=day.leg_id)
                    except ValidationError:
                        TripDay.objects.filter(pk=day.pk).update(leg_id=None)
            else:
                pairs = []
                if target > day.date:
                    for d in days:
                        if day.date < d.date <= target:
                            pairs.append((d, d.date - timedelta(days=1)))
                else:
                    for d in days:
                        if target <= d.date < day.date:
                            pairs.append((d, d.date + timedelta(days=1)))
                pairs.append((day, target))
                target_leg_id = occupant.leg_id if occupant else day.leg_id
                _reassign_day_dates(pairs)
                if occupant and occupant.leg_id != day.leg_id:
                    TripDay.objects.filter(pk=day.pk).update(leg_id=target_leg_id)
                elif not occupant and day.leg_id is not None:
                    after_days = list(trip.days.order_by('date', 'id'))
                    try:
                        validate_contiguous_legs(trip, [d.leg_id for d in after_days], target_leg_id=day.leg_id)
                    except ValidationError:
                        TripDay.objects.filter(pk=day.pk).update(leg_id=None)
            _renumber_days(trip)
            sync_leg_order(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)

    @action(detail=True, methods=['post'], url_path='adjust-leg')
    def adjust_leg(self, request, pk=None):
        """Extend/shorten a leg by 1 day (with ripple or borrow) or reorder a leg up/down."""
        trip = self.get_object()
        self._require_edit(trip)
        leg = trip.legs.filter(pk=request.data.get('leg_id')).first()
        if not leg:
            return Response({'leg_id': 'Leg not found on this trip.'}, status=status.HTTP_400_BAD_REQUEST)
        act = request.data.get('action')
        ripple = bool(request.data.get('ripple', True))
        with transaction.atomic():
            days = list(trip.days.order_by('date', 'id'))
            leg_days = [d for d in days if d.leg_id == leg.pk]
            if act == 'add_day':
                if leg_days:
                    after = leg_days[-1].date
                    target = after + timedelta(days=1)
                    if ripple:
                        to_shift = [(d, d.date + timedelta(days=1)) for d in days if d.date >= target]
                        _reassign_day_dates(to_shift)
                        TripDay.objects.create(user=trip.user, trip=trip, date=target, leg=leg, title=leg.name)
                    else:
                        next_day = next((d for d in days if d.date > after), None)
                        if next_day:
                            TripDay.objects.filter(pk=next_day.pk).update(leg=leg)
                        else:
                            TripDay.objects.create(user=trip.user, trip=trip, date=target, leg=leg, title=leg.name)
                else:
                    target = (days[-1].date + timedelta(days=1)) if days else (trip.start_date or parse_date('2027-01-01'))
                    TripDay.objects.create(user=trip.user, trip=trip, date=target, leg=leg, title=leg.name)
            elif act == 'remove_day':
                if not leg_days:
                    return Response({'detail': 'Leg has no days to remove.'}, status=status.HTTP_400_BAD_REQUEST)
                victim = leg_days[-1]
                removed_date = victim.date
                victim.delete()
                if ripple:
                    later = list(trip.days.filter(date__gt=removed_date).order_by('date', 'id'))
                    _reassign_day_dates([(d, d.date - timedelta(days=1)) for d in later])
            elif act in ('move_up', 'move_down'):
                ordered_legs = list(trip.legs.order_by('sort_order', 'id'))
                idx = next((i for i, l in enumerate(ordered_legs) if l.pk == leg.pk), None)
                swap_idx = idx - 1 if act == 'move_up' else idx + 1
                if idx is None or swap_idx < 0 or swap_idx >= len(ordered_legs):
                    return self._trip_response(request, trip)
                other = ordered_legs[swap_idx]
                ordered_legs[idx], ordered_legs[swap_idx] = ordered_legs[swap_idx], ordered_legs[idx]
                for i, l in enumerate(ordered_legs):
                    if l.sort_order != i:
                        TripLeg.objects.filter(pk=l.pk).update(sort_order=i)
                first_leg, second_leg = (leg, other) if act == 'move_up' else (other, leg)
                first_days = [d for d in days if d.leg_id == first_leg.pk]
                second_days = [d for d in days if d.leg_id == second_leg.pk]
                combined = sorted(first_days + second_days, key=lambda d: d.date)
                if first_days and second_days:
                    slot_dates = [d.date for d in combined]
                    new_order = first_days + second_days
                    _reassign_day_dates(list(zip(new_order, slot_dates)))
            else:
                return Response({'action': 'Expected add_day, remove_day, move_up, or move_down.'}, status=status.HTTP_400_BAD_REQUEST)
            _renumber_days(trip)
            sync_leg_order(trip)
            trip.sync_dates_from_days()
        return self._trip_response(request, trip)


class TripLegViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripLeg.objects.select_related('trip').prefetch_related('days')
    serializer_class = TripLegSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        return qs


class TripLodgingViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripLodging.objects.select_related('trip').prefetch_related('days', 'attachments__asset')
    serializer_class = TripLodgingSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        return qs


class TripDayViewSet(TripAccessMixin, viewsets.ModelViewSet):
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
        trip = self._resolve_trip_from_validated(serializer.validated_data)
        self._require_edit(trip)
        day = serializer.save(user=trip.user)
        _renumber_days(day.trip)
        day.trip.sync_dates_from_days()

    def perform_update(self, serializer):
        self._require_edit(serializer.instance.trip)
        day = serializer.save()
        _renumber_days(day.trip)
        day.trip.sync_dates_from_days()

    def perform_destroy(self, instance):
        trip = instance.trip
        self._require_edit(trip)
        instance.delete()
        _renumber_days(trip)
        trip.sync_dates_from_days()

    @action(detail=True, methods=['post'], url_path='bulk-stops')
    def bulk_stops(self, request, pk=None):
        day = self.get_object()
        self._require_edit(day.trip)
        items = request.data.get('items')
        if not isinstance(items, list):
            return Response({'items': 'Expected a list of rows.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = {stop.id: stop for stop in day.stops.all()}
        keep_ids = []
        with transaction.atomic():
            for index, raw in enumerate(items):
                if not isinstance(raw, dict):
                    return Response(
                        {'items': f'Row {index + 1} must be an object.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                payload = {
                    'day_id': day.id,
                    'kind': raw.get('kind') or TripStop.KIND_ACTIVITY,
                    'travel_mode': raw.get('travel_mode') or '',
                    'text': raw.get('text') or '',
                    'loc': raw.get('loc') or '',
                    'arrive_loc': raw.get('arrive_loc') or '',
                    'start_time': raw.get('start_time') or None,
                    'duration_minutes': raw.get('duration_minutes'),
                    'sort_order': index,
                }
                for key in ('price', 'currency', 'person', 'timezone', 'arrive_timezone'):
                    if key in raw:
                        payload[key] = raw[key] if key == 'price' else (raw[key] or '')
                if payload['kind'] == TripStop.KIND_TRAVEL and not payload['travel_mode']:
                    payload['travel_mode'] = TripStop.TRAVEL_DRIVE
                stop_id = raw.get('id')
                instance = existing.get(stop_id) if stop_id else None
                if instance is None:
                    payload['cat'] = {TripStop.KIND_TRAVEL: 'Travel', TripStop.KIND_EVENT: 'Event'}.get(
                        payload['kind'], 'Sight'
                    )
                    serializer = TripStopSerializer(data=payload, context={'request': request})
                else:
                    serializer = TripStopSerializer(
                        instance,
                        data=payload,
                        partial=True,
                        context={'request': request},
                    )
                serializer.is_valid(raise_exception=True)
                stop = serializer.save(user=day.trip.user, day=day, sort_order=index)
                keep_ids.append(stop.id)
            for stop_id, stop in existing.items():
                if stop_id not in keep_ids:
                    stop.delete()

        day.refresh_from_db()
        return Response(TripDaySerializer(day, context={'request': request}).data)


def _next_stop_order(day=None, trip=None, exclude_pk=None):
    if day is not None:
        qs = day.stops.all()
    else:
        qs = TripStop.objects.filter(trip=trip, day__isnull=True)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    max_order = qs.order_by('-sort_order').values_list('sort_order', flat=True).first()
    return 0 if max_order is None else max_order + 1


class TripStopViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripStop.objects.select_related('day', 'trip', 'leg')
    serializer_class = TripStopSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        day_id = self.request.query_params.get('day')
        trip_id = self.request.query_params.get('trip')
        unscheduled = self.request.query_params.get('unscheduled')
        if day_id:
            qs = qs.filter(day_id=day_id)
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        if unscheduled in ('1', 'true', 'True'):
            qs = qs.filter(day__isnull=True)
        return qs

    def perform_create(self, serializer):
        trip = self._resolve_trip_from_validated(serializer.validated_data)
        self._require_edit(trip)
        stop = serializer.save(user=trip.user)
        if 'sort_order' not in serializer.validated_data:
            stop.sort_order = _next_stop_order(day=stop.day, trip=stop.trip, exclude_pk=stop.pk)
            stop.save(update_fields=['sort_order'])

    def perform_update(self, serializer):
        self._require_edit(serializer.instance.trip)
        old_day_id = serializer.instance.day_id
        stop = serializer.save()
        if stop.day_id != old_day_id:
            stop.sort_order = _next_stop_order(day=stop.day, trip=stop.trip, exclude_pk=stop.pk)
            stop.save(update_fields=['sort_order'])

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        stop = self.get_object()
        self._require_edit(stop.trip)
        direction = request.data.get('direction')
        if direction not in ('up', 'down'):
            return Response({'direction': 'Must be "up" or "down".'}, status=status.HTTP_400_BAD_REQUEST)
        if stop.day_id is not None:
            siblings = list(stop.day.stops.order_by('sort_order', 'id'))
        else:
            siblings = list(TripStop.objects.filter(trip_id=stop.trip_id, day__isnull=True).order_by('sort_order', 'id'))
        idx = next(i for i, row in enumerate(siblings) if row.pk == stop.pk)
        swap = idx - 1 if direction == 'up' else idx + 1
        if 0 <= swap < len(siblings):
            siblings[idx], siblings[swap] = siblings[swap], siblings[idx]
            for i, row in enumerate(siblings):
                if row.sort_order != i:
                    row.sort_order = i
                    row.save(update_fields=['sort_order'])
        return Response(self.get_serializer(stop).data)


class TripTodoViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripTodo.objects.all()
    serializer_class = TripTodoSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        return qs.filter(trip_id=trip_id) if trip_id else qs


class TripSuggestionBatchViewSet(
    TripAccessMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """AI assistant requests. Creating one queues a background task; poll it until ``status`` is not running."""

    queryset = TripSuggestionBatch.objects.prefetch_related('suggestions')
    serializer_class = TripSuggestionBatchSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        trip_id = self.request.query_params.get('trip')
        return qs.filter(trip_id=trip_id) if trip_id else qs

    def list(self, request, *args, **kwargs):
        rows = self.filter_queryset(self.get_queryset())[:20]
        return Response(self.get_serializer(rows, many=True).data)

    def perform_create(self, serializer):
        trip = self._resolve_trip_from_validated(serializer.validated_data)
        self._require_edit(trip)
        if not llm_available():
            raise ValidationError({'detail': 'No AI model is configured. Set OPENAI_API_KEY or LOCALAI_URL.'})
        batch = serializer.save(user=trip.user)
        transaction.on_commit(lambda: generate_suggestions.delay(batch.id))


class TripSuggestionViewSet(TripAccessMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TripSuggestion.objects.select_related('batch__trip')
    serializer_class = TripSuggestionSerializer
    pagination_class = None
    trip_lookup = 'batch__trip'

    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        """Create the stop/event or lodging. Optional ``fields`` carry the user's edits."""
        suggestion = self.get_object()
        self._require_edit(suggestion.batch.trip)
        with transaction.atomic():
            trip_ai.apply_suggestion(suggestion, request, request.data.get('fields'))
        return Response(self.get_serializer(suggestion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        suggestion = self.get_object()
        self._require_edit(suggestion.batch.trip)
        if suggestion.status == TripSuggestion.STATUS_PENDING:
            suggestion.status = TripSuggestion.STATUS_DISMISSED
            suggestion.save(update_fields=['status', 'modified_on'])
        return Response(self.get_serializer(suggestion).data)


class TripMediaViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripMedia.objects.select_related('asset', 'trip', 'day', 'stop')
    serializer_class = TripMediaSerializer
    pagination_class = None

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return TripMedia.objects.none()
        trips = self._accessible_trips(write=False)
        return TripMedia.objects.select_related('asset', 'trip', 'day', 'stop').filter(
            Q(trip__in=trips) | Q(day__trip__in=trips) | Q(stop__trip__in=trips)
        ).distinct()


class TripStopAttachmentViewSet(TripAccessMixin, viewsets.ModelViewSet):
    queryset = TripStopAttachment.objects.select_related('stop', 'lodging', 'asset')
    serializer_class = TripStopAttachmentSerializer
    pagination_class = None

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return TripStopAttachment.objects.none()
        trips = self._accessible_trips(write=False)
        qs = TripStopAttachment.objects.select_related('stop', 'lodging', 'asset').filter(
            Q(stop__trip__in=trips) | Q(lodging__trip__in=trips)
        ).distinct()
        stop_id = self.request.query_params.get('stop')
        lodging_id = self.request.query_params.get('lodging')
        if stop_id:
            qs = qs.filter(stop_id=stop_id)
        if lodging_id:
            qs = qs.filter(lodging_id=lodging_id)
        return qs

    @action(detail=False, methods=['get'])
    def documents(self, request):
        """Each uploaded document once (newest first), with its trip, for attaching it elsewhere."""
        qs = (
            self.get_queryset()
            .filter(kind=TripStopAttachment.KIND_DOCUMENT)
            .select_related('stop__trip', 'lodging__trip', 'asset')
            .order_by('-created_at')
        )
        seen = set()
        out = []
        for item in qs:
            key = ('asset', item.asset_id) if item.asset_id else ('url', item.url)
            if not (item.asset_id or item.url) or key in seen:
                continue
            seen.add(key)
            trip = item.stop.trip if item.stop_id else item.lodging.trip
            out.append({
                'id': item.id,
                'title': item.title,
                'asset_id': item.asset_id,
                'url': '' if item.asset_id else item.url,
                'file_url': item.asset.url if item.asset_id else item.url,
                'trip_id': trip.id,
                'trip_title': trip.title,
            })
        return Response(out)


class TripShareViewSet(viewsets.ModelViewSet):
    """Owner-only collaborator management (plus collaborator self-removal on DELETE)."""

    queryset = TripShare.objects.select_related('trip', 'user')
    serializer_class = TripShareSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return TripShare.objects.none()
        email = (getattr(user, 'email', '') or '').strip().lower()
        own_share_q = Q(user=user) | (Q(email__iexact=email) if email else Q(pk__in=[]))
        if self.action == 'destroy':
            qs = TripShare.objects.select_related('trip', 'user').filter(
                Q(trip__in=owned_trips(user)) | own_share_q
            ).distinct()
        else:
            qs = TripShare.objects.select_related('trip', 'user').filter(trip__in=owned_trips(user))
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        return qs

    def create(self, request, *args, **kwargs):
        from .emails import send_trip_invite_email

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = serializer.validated_data.get('trip')
        if not trip or not is_trip_owner(trip, request.user):
            raise PermissionDenied('Only the trip owner can invite collaborators.')
        share = serializer.save(invited_by=request.user)
        email_status = send_trip_invite_email(share, request=request)
        data = dict(self.get_serializer(share).data)
        data['email_status'] = email_status
        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='resend')
    def resend(self, request, pk=None):
        from .emails import send_trip_invite_email

        share = self.get_object()
        if not is_trip_owner(share.trip, request.user):
            raise PermissionDenied('Only the trip owner can resend invitations.')
        email_status = send_trip_invite_email(share, request=request)
        data = dict(self.get_serializer(share).data)
        data['email_status'] = email_status
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='resolve-invite')
    def resolve_invite(self, request):
        token = (request.query_params.get('token') or '').strip()
        if not token:
            return Response({'detail': 'Invitation token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        share = TripShare.objects.select_related('trip', 'trip__user').filter(invite_token=token).first()
        if share is None:
            return Response({'detail': 'This invitation link is invalid or has been revoked.'}, status=status.HTTP_404_NOT_FOUND)
        user = request.user
        user_email = (getattr(user, 'email', '') or '').strip().lower()
        is_recipient = (share.user_id == user.id) or (bool(user_email) and share.email.lower() == user_email)
        if not is_recipient and not is_trip_owner(share.trip, user):
            return Response(
                {'detail': f'This invitation was sent to {share.email}. Sign in with that email to open the trip.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if is_recipient and share.user_id is None:
            share.user = user
            share.save(update_fields=['user', 'modified_on'])
        trip = Trip.objects.select_related('user').prefetch_related(*_trip_detail_prefetches()).get(pk=share.trip_id)
        return Response(TripSerializer(trip, context={'request': request}).data)

    def perform_update(self, serializer):
        if not is_trip_owner(serializer.instance.trip, self.request.user):
            raise PermissionDenied('Only the trip owner can change collaborator roles.')
        serializer.save()


class TripCommentViewSet(viewsets.ModelViewSet):
    """Threaded comments at Trip / Leg / Day / Stop / Lodging levels, with Resolve / Reopen."""

    queryset = TripComment.objects.select_related('author', 'resolved_by', 'trip', 'leg', 'day', 'stop', 'lodging')
    serializer_class = TripCommentSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return TripComment.objects.none()
        trips = accessible_trips(user, write=False)
        qs = TripComment.objects.select_related(
            'author', 'resolved_by', 'trip', 'leg', 'day', 'stop', 'lodging'
        ).filter(trip__in=trips)
        trip_id = self.request.query_params.get('trip')
        if trip_id:
            qs = qs.filter(trip_id=trip_id)
        resolved = self.request.query_params.get('resolved')
        if resolved in ('true', '1', 'True'):
            qs = qs.filter(Q(parent__isnull=True, resolved=True) | Q(parent__resolved=True))
        elif resolved in ('false', '0', 'False'):
            qs = qs.filter(Q(parent__isnull=True, resolved=False) | Q(parent__resolved=False))
        target_type = self.request.query_params.get('target_type')
        if target_type == TripComment.TARGET_TRIP:
            qs = qs.filter(leg__isnull=True, day__isnull=True, stop__isnull=True, lodging__isnull=True)
        elif target_type == TripComment.TARGET_LEG:
            qs = qs.filter(leg__isnull=False)
        elif target_type == TripComment.TARGET_DAY:
            qs = qs.filter(day__isnull=False)
        elif target_type == TripComment.TARGET_STOP:
            qs = qs.filter(stop__isnull=False)
        elif target_type == TripComment.TARGET_LODGING:
            qs = qs.filter(lodging__isnull=False)
        for param in ('leg', 'day', 'stop', 'lodging'):
            val = self.request.query_params.get(param)
            if val:
                qs = qs.filter(**{f'{param}_id': val})
        return qs

    def perform_create(self, serializer):
        from .emails import send_trip_comment_emails

        trip = serializer.validated_data.get('trip')
        if not trip or not can_view_trip(trip, self.request.user):
            raise PermissionDenied('You do not have access to comment on this trip.')
        comment = serializer.save(author=self.request.user)
        if trip.notify_on_comments:
            send_trip_comment_emails(comment, request=self.request)

    def _can_toggle_resolved(self, comment, user):
        return can_edit_trip(comment.trip, user) or comment.author_id == user.id

    def perform_update(self, serializer):
        instance = serializer.instance
        user = self.request.user
        data = serializer.validated_data
        if 'body' in data and instance.author_id != user.id:
            raise PermissionDenied('Only the comment author can edit the text.')
        extra = {}
        if 'resolved' in data and data['resolved'] != instance.resolved:
            if not self._can_toggle_resolved(instance, user):
                raise PermissionDenied('You do not have permission to resolve or reopen this thread.')
            if data['resolved']:
                extra['resolved_at'] = dj_timezone.now()
                extra['resolved_by'] = user
            else:
                extra['resolved_at'] = None
                extra['resolved_by'] = None
        serializer.save(**extra)

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.author_id != user.id and not is_trip_owner(instance.trip, user):
            raise PermissionDenied('Only the author or trip owner can delete this comment.')
        instance.delete()

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        comment = self.get_object()
        root = comment.parent if comment.parent_id else comment
        if not self._can_toggle_resolved(root, request.user):
            raise PermissionDenied('You do not have permission to resolve this thread.')
        root.resolved = True
        root.resolved_at = dj_timezone.now()
        root.resolved_by = request.user
        root.save(update_fields=['resolved', 'resolved_at', 'resolved_by', 'modified_on'])
        return Response(self.get_serializer(root).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        comment = self.get_object()
        root = comment.parent if comment.parent_id else comment
        if not self._can_toggle_resolved(root, request.user):
            raise PermissionDenied('You do not have permission to reopen this thread.')
        root.resolved = False
        root.resolved_at = None
        root.resolved_by = None
        root.save(update_fields=['resolved', 'resolved_at', 'resolved_by', 'modified_on'])
        return Response(self.get_serializer(root).data)


class PublicTripView(APIView):
    """Unauthenticated read-only trip endpoint addressed by an obfuscated share token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        trip = get_object_or_404(
            Trip.objects.select_related('user').prefetch_related(*_trip_detail_prefetches()),
            share_token=token,
            public_enabled=True,
        )
        return Response(PublicTripSerializer(trip).data)

