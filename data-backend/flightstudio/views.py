import re

from django.conf import settings
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .core.drone_orbit import OrbitSpec, apply_orbit
from .core.earth_studio import earth_studio_document
from .core.geocode import reverse_place, search_places
from .core.locations import LOCATIONS, Location
from .core.map_doc import MapDocument, empty_map_document
from .core.retime import smooth_timing, worst_speed_jump
from .core.program import GeoPoint, PathProgram
from .core.program_demos import build_demo, list_demos
from .core.program_geom import ProgramError
from .core.program_time import fit_program_duration
from .core.schema import CameraKeyframe, Entity, PathDocument
from .core.templates import starter_at
from .core.validate import validate
from .models import FlightPath
from .preview import preview, preview_program
from .program_preview import DEFAULT_STEP_M, program_preview

SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
SIM_UNAVAILABLE = (
    'Simulator is not available in this app. Run FlightStudio next to MSFS 2024 for Play/Record.'
)


def _error(detail, code=status.HTTP_400_BAD_REQUEST):
    if not isinstance(detail, str):
        detail = str(detail)
    return Response({'detail': detail}, status=code)


def _parse_document(data):
    if not isinstance(data, dict):
        raise ValueError('Request body must be a path document.')
    try:
        return PathDocument.model_validate(data)
    except ValidationError as exc:
        raise ValueError(exc.errors()) from exc


def _dump(model):
    return model.model_dump(mode='json')


def _jsonable_errors(errors):
    """Strip pydantic's `ctx`, which can hold exception objects DRF cannot render."""
    return [
        {key: value for key, value in error.items() if key != 'ctx'}
        for error in errors
    ]


def _is_program(row):
    return isinstance(row.program, dict) and bool(row.program)


def _program_stub(path_id):
    """Minimal document so list/summary still have a meta.path_id."""
    return {
        'meta': {
            'path_id': path_id,
            'kind': 'program',
            'entity': 'USER_AIRCRAFT',
            'duration_seconds': 0,
        },
        'flight_keyframes': [],
        'camera_keyframes': [],
        'systems': [],
    }


def _program_payload(row):
    return {
        'kind': 'program',
        'path_id': row.path_id,
        'program': row.program,
    }


def _summary(row):
    if _is_program(row):
        segments = row.program.get('segments') if isinstance(row.program, dict) else None
        cameras = row.program.get('camera_keyframes') if isinstance(row.program, dict) else None
        return {
            'path_id': row.path_id,
            'kind': 'program',
            'duration': 0,
            'flight_keyframes': len(segments) if isinstance(segments, list) else 0,
            'camera_keyframes': len(cameras) if isinstance(cameras, list) else 0,
            'entity': 'USER_AIRCRAFT',
        }
    raw = row.document if isinstance(row.document, dict) else {}
    meta = raw.get('meta') if isinstance(raw.get('meta'), dict) else {}
    flight = raw.get('flight_keyframes') if isinstance(raw.get('flight_keyframes'), list) else []
    camera = raw.get('camera_keyframes') if isinstance(raw.get('camera_keyframes'), list) else []
    duration = meta.get('duration_seconds')
    if not duration and flight and isinstance(flight[-1], dict):
        duration = flight[-1].get('time_offset') or 0
    return {
        'path_id': row.path_id,
        'kind': 'waypoint',
        'duration': duration or 0,
        'flight_keyframes': len(flight),
        'camera_keyframes': len(camera),
        'entity': meta.get('entity') or 'USER_AIRCRAFT',
    }


def _owned(request, path_id):
    return FlightPath.objects.filter(owner=request.user, path_id=path_id).first()


@api_view(['GET'])
def capabilities(request):
    return Response({
        'sim': False,
        'earth_studio': True,
        'map2d': True,
        'map3d': True,
        'maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '') or '',
    })


@api_view(['GET'])
def locations(request):
    return Response([
        {
            'key': key,
            'label': place.label,
            'lat': place.lat,
            'lon': place.lon,
            'alt_ft_msl': place.alt_ft_msl,
            'heading_deg_true': place.heading_deg_true,
        }
        for key, place in LOCATIONS.items()
    ])


@api_view(['GET'])
def geocode_search(request):
    query = (request.query_params.get('q') or '').strip()
    if len(query) < 2:
        return _error('q must be at least 2 characters.')
    try:
        results = search_places(query, viewbox=request.query_params.get('viewbox'))
    except RuntimeError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
    return Response({'results': results})


@api_view(['GET'])
def geocode_reverse(request):
    try:
        lat = float(request.query_params.get('lat'))
        lon = float(request.query_params.get('lon'))
    except (TypeError, ValueError):
        return _error('lat and lon are required.')
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return _error('lat/lon out of range.')
    try:
        hit = reverse_place(lat, lon)
    except RuntimeError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
    if hit is None:
        return Response({'label': None, 'lat': lat, 'lon': lon})
    return Response(hit)


@api_view(['GET'])
def list_paths(request):
    rows = FlightPath.objects.filter(owner=request.user)
    return Response([_summary(row) for row in rows])


def _origin_at(place: Location) -> GeoPoint:
    return GeoPoint(lat=place.lat, lon=place.lon, alt_ft_msl=place.alt_ft_msl)


@api_view(['GET'])
def program_demos(request):
    return Response({'demos': list_demos()})


@api_view(['POST'])
def new_path(request):
    path_id = (request.data.get('path_id') or '').strip()
    location = request.data.get('location') or 'manhattan'
    duration = request.data.get('duration', 36.0)
    kind = (request.data.get('kind') or 'waypoint').strip().lower()
    try:
        entity = Entity(request.data.get('entity') or Entity.USER_AIRCRAFT)
    except ValueError:
        return _error('Unknown entity.')
    if not SAFE_ID.match(path_id):
        return _error('path_id must be letters, digits, dot, dash or underscore.')
    if location not in LOCATIONS:
        return _error(f'Unknown location {location!r}.', status.HTTP_404_NOT_FOUND)
    if FlightPath.objects.filter(owner=request.user, path_id=path_id).exists():
        return _error(f'A path called {path_id!r} already exists.')
    if kind == 'program':
        demo = (request.data.get('demo') or 'figure-eight').strip()
        try:
            program = build_demo(demo)
        except ValueError as exc:
            return _error(str(exc))
        # Re-home demos whose first pen is relative (LineTo/Arc). Absolute
        # Hermite/Spline demos keep their authored points near Berkeley.
        if not any(seg.kind in ('HERMITE', 'SPLINE') for seg in program.segments):
            program = program.model_copy(update={'origin': _origin_at(LOCATIONS[location])})
        target = request.data.get('fit_duration_s', duration)
        try:
            if target:
                program = fit_program_duration(program, float(target))
        except (ProgramError, TypeError, ValueError) as exc:
            return _error(str(exc))
        dumped = _dump(program)
        FlightPath.objects.create(
            owner=request.user,
            path_id=path_id,
            document=_program_stub(path_id),
            program=dumped,
            map_overlay=_dump(empty_map_document(path_id)),
        )
        return Response(
            {'kind': 'program', 'path_id': path_id, 'program': dumped},
            status=status.HTTP_201_CREATED,
        )
    if kind not in ('waypoint', ''):
        return _error(f'Unknown kind {kind!r}; use waypoint or program.')
    try:
        document = starter_at(path_id, location, float(duration), entity)
        document.meta.duration_seconds = document.duration
    except (TypeError, ValueError) as exc:
        return _error(str(exc))
    FlightPath.objects.create(
        owner=request.user,
        path_id=path_id,
        document=_dump(document),
        map_overlay=_dump(empty_map_document(path_id)),
    )
    return Response(_dump(document), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
def path_detail(request, path_id):
    row = _owned(request, path_id)
    if row is None:
        return _error(f'No path called {path_id!r}.', status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        if _is_program(row):
            return Response(_program_payload(row))
        try:
            return Response(_dump(_parse_document(row.document)))
        except ValueError:
            return Response(row.document)
    if request.method == 'DELETE':
        row.delete()
        return Response({'deleted': True})
    if _is_program(row) or (isinstance(request.data, dict) and request.data.get('kind') == 'program'):
        # Program document: persist the segment program (stage 7 editing).
        body = request.data if isinstance(request.data, dict) else {}
        try:
            program = PathProgram.model_validate(body.get('program', body))
        except ValidationError as exc:
            return Response(
                {'detail': 'The program is not valid.',
                 'errors': _jsonable_errors(exc.errors())},
                status=status.HTTP_400_BAD_REQUEST,
            )
        row.program = _dump(program)
        row.document = _program_stub(path_id)
        row.save(update_fields=['program', 'document', 'updated_at'])
        return Response(_program_payload(row))
    try:
        document = _parse_document(request.data)
    except ValueError as exc:
        return _error(exc)
    if document.meta.path_id != path_id:
        return _error('Path id in the body does not match the URL.')
    document.meta.duration_seconds = document.duration
    row.document = _dump(document)
    row.program = None
    row.save(update_fields=['document', 'program', 'updated_at'])
    return Response(row.document)


@api_view(['GET', 'PUT'])
def path_map(request, path_id):
    row = _owned(request, path_id)
    if row is None:
        return _error(f'No path called {path_id!r}.', status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        if row.map_overlay:
            return Response(row.map_overlay)
        return Response(_dump(empty_map_document(path_id)))
    try:
        overlay = MapDocument.model_validate(request.data)
    except ValidationError as exc:
        return _error(exc.errors())
    if overlay.path_id != path_id:
        return _error('Path id in the body does not match the URL.')
    row.map_overlay = _dump(overlay)
    row.save(update_fields=['map_overlay', 'updated_at'])
    return Response(row.map_overlay)


@api_view(['POST'])
def validate_document(request):
    try:
        document = _parse_document(request.data)
    except ValueError as exc:
        return _error(exc)
    return Response(validate(document))


@api_view(['POST'])
def preview_document(request):
    try:
        document = _parse_document(request.data)
    except ValueError as exc:
        return _error(exc)
    return Response(preview(document))


@api_view(['POST'])
def preview_program_document(request):
    """Program-mode preview in the existing sample format. See SEGMENT_MODEL.md §2.

    Same shape as ``paths/preview/`` — duration, samples, camera_track — so the
    map, 3D view and exporters can consume a PathProgram without knowing it is
    one. Samples carry ``break_before`` at a mid-path MoveTo.
    """
    body = request.data if isinstance(request.data, dict) else {}
    try:
        program = PathProgram.model_validate(body.get('program', body))
    except ValidationError as exc:
        errors = exc.errors()
        return Response(
            {'detail': 'The program is not valid.', 'errors': _jsonable_errors(errors),
             'index': _segment_index(errors)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return Response(preview_program(program, samples=int(body.get('samples', 240))))
    except ProgramError as exc:
        return Response(
            {'detail': str(exc), 'index': exc.index, 'segment_id': exc.segment_id},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except (TypeError, ValueError) as exc:
        return _error(exc)


def _segment_index(errors):
    """Pull the offending segment out of a pydantic error location, if it names one.

    Locations look like ('segments', 2, 'ArcSegment', 'radius_m'), so the
    harness can highlight the row rather than printing a path at the user.
    """
    for error in errors:
        location = error.get('loc') or ()
        if len(location) >= 2 and location[0] == 'segments' and isinstance(location[1], int):
            return location[1]
    return None


@api_view(['POST'])
def evaluate_program(request):
    """Evaluate a segment path program. See SEGMENT_MODEL.md.

    Backs the harness page with distance-spaced samples and per-segment
    diagnostics. For the player-shaped payload see ``program/preview/``.
    Constraints are solved first, so the payload always carries
    `solved_program` — what was actually drawn. Pass `fit_duration_s` to
    retime the whole program to a total first.
    """
    body = request.data if isinstance(request.data, dict) else {}
    try:
        program = PathProgram.model_validate(body.get('program', body))
    except ValidationError as exc:
        errors = exc.errors()
        return Response(
            {'detail': 'The program is not valid.', 'errors': _jsonable_errors(errors),
             'index': _segment_index(errors)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    target = body.get('fit_duration_s')
    try:
        if target:
            program = fit_program_duration(program, float(target))
        preview = program_preview(program, step_m=body.get('step_m', DEFAULT_STEP_M))
    except ProgramError as exc:
        return Response(
            {'detail': str(exc), 'index': exc.index, 'segment_id': exc.segment_id},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError as exc:
        return _error(exc)
    return Response(preview)


@api_view(['POST'])
def smooth_path_timing(request):
    try:
        document = _parse_document(request.data.get('document') if isinstance(request.data, dict) and 'document' in request.data else request.data)
    except ValueError as exc:
        return _error(exc)
    window = request.data.get('window_s', 10.0) if isinstance(request.data, dict) else 10.0
    frames = document.flight_keyframes
    if len(frames) < 3:
        return _error('Smoothing the timing needs at least three waypoints.', status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        retimed = smooth_timing(frames, float(window))
    except (TypeError, ValueError) as exc:
        return _error(str(exc))
    before = sorted(frames, key=lambda key: key.time_offset)
    moved = max(abs(a.time_offset - b.time_offset) for a, b in zip(before, retimed))
    return Response({
        'flight_keyframes': [key.model_dump(mode='json') for key in retimed],
        'worst_jump_before': round(worst_speed_jump(before), 2),
        'worst_jump_after': round(worst_speed_jump(retimed), 2),
        'largest_move_s': round(moved, 2),
    })


@api_view(['POST'])
def export_earth_studio(request):
    try:
        document = _parse_document(request.data)
        payload = earth_studio_document(document)
    except ValueError as exc:
        return _error(str(exc))
    return Response(payload)


@api_view(['POST'])
def camera_orbit(request):
    data = request.data if isinstance(request.data, dict) else {}
    frames = data.get('camera_keyframes') or []
    try:
        spec = OrbitSpec.model_validate({k: v for k, v in data.items() if k != 'camera_keyframes'})
        existing = [CameraKeyframe.model_validate(frame) for frame in frames]
        result = apply_orbit(existing, spec)
    except (ValidationError, ValueError) as exc:
        return _error(exc.errors() if isinstance(exc, ValidationError) else str(exc))
    return Response({'camera_keyframes': [key.model_dump(mode='json') for key in result]})


@api_view(['GET', 'PUT', 'POST'])
def sim_unavailable(request, rest=None):
    return _error(SIM_UNAVAILABLE, status.HTTP_409_CONFLICT)
