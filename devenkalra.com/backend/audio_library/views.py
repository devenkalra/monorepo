from pathlib import Path

from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .indexer import index_roots
from .models import AudioTrack
from .permissions import IsSuperuserRole
from .roots import configured_roots, content_type_for, cover_file, resolve_track_file, verify_stream_signature
from .serializers import AudioTrackSerializer


class AudioPagination(PageNumberPagination):
    page_size = 200
    page_size_query_param = 'page_size'
    max_page_size = 1000


class IsAuthenticatedOrSignedStream(permissions.BasePermission):
    def has_permission(self, request, view):
        if getattr(view, 'action', None) in ('stream', 'cover'):
            return True
        return bool(request.user and request.user.is_authenticated)


class _LimitedReader:
    def __init__(self, handle, length, chunk_size=8192):
        self.handle = handle
        self.remaining = length
        self.chunk_size = chunk_size

    def __iter__(self):
        while self.remaining > 0:
            data = self.handle.read(min(self.chunk_size, self.remaining))
            if not data:
                break
            self.remaining -= len(data)
            yield data

    def close(self):
        self.handle.close()


def ranged_file_response(request, path: Path, content_type: str):
    file_size = path.stat().st_size
    range_header = request.headers.get('Range')
    if not range_header:
        response = FileResponse(path.open('rb'), content_type=content_type)
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        return response

    if not range_header.startswith('bytes='):
        return HttpResponse(status=416)
    spec = range_header.removeprefix('bytes=').split(',')[0].strip()
    start_s, _, end_s = spec.partition('-')
    try:
        if start_s == '' and end_s:
            start = max(file_size - int(end_s), 0)
            end = file_size - 1
        else:
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return HttpResponse(status=416)
    if start < 0 or end < start or start >= file_size:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{file_size}'
        return response
    end = min(end, file_size - 1)
    length = end - start + 1
    handle = path.open('rb')
    handle.seek(start)
    response = StreamingHttpResponse(
        _LimitedReader(handle, length),
        status=206,
        content_type=content_type,
    )
    response['Content-Length'] = str(length)
    response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    response['Accept-Ranges'] = 'bytes'
    return response


class AudioTrackViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticatedOrSignedStream]
    serializer_class = AudioTrackSerializer
    pagination_class = AudioPagination
    queryset = AudioTrack.objects.all()

    def get_queryset(self):
        qs = AudioTrack.objects.all()
        folder = self.request.query_params.get('folder')
        artist = self.request.query_params.get('artist')
        composer = self.request.query_params.get('composer')
        genre = self.request.query_params.get('genre')
        album = self.request.query_params.get('album')
        year = self.request.query_params.get('year')
        parent = self.request.query_params.get('parent')
        q = self.request.query_params.get('q')
        if folder:
            qs = qs.filter(folder_slug=folder)
        if artist:
            qs = qs.filter(artist=artist)
        if composer:
            qs = qs.filter(composer=composer)
        if genre:
            qs = qs.filter(genre=genre)
        if album:
            qs = qs.filter(album=album)
        if year:
            try:
                qs = qs.filter(year=int(year))
            except (TypeError, ValueError):
                qs = qs.none()
        if parent:
            qs = qs.filter(Q(parent=parent) | Q(parent__startswith=f'{parent}/'))
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(artist__icontains=q)
                | Q(composer__icontains=q)
                | Q(genre__icontains=q)
                | Q(album__icontains=q)
                | Q(filename__icontains=q)
                | Q(relpath__icontains=q)
            )
        return qs

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], authentication_classes=[])
    def stream(self, request, pk=None):
        track = AudioTrack.objects.filter(pk=pk).first()
        if track is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        sig = request.query_params.get('sig', '')
        if not verify_stream_signature(sig, track.id):
            return Response({'detail': 'Invalid or expired stream link.'}, status=status.HTTP_403_FORBIDDEN)
        path = resolve_track_file(track)
        if path is None:
            return Response({'detail': 'File is not available.'}, status=status.HTTP_404_NOT_FOUND)
        return ranged_file_response(request, path, content_type_for(path))

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], authentication_classes=[])
    def cover(self, request, pk=None):
        track = AudioTrack.objects.filter(pk=pk).first()
        if track is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        sig = request.query_params.get('sig', '')
        if not verify_stream_signature(sig, track.id):
            return Response({'detail': 'Invalid or expired stream link.'}, status=status.HTTP_403_FORBIDDEN)
        path = cover_file(track.id)
        if not path.is_file():
            return Response({'detail': 'No cover art.'}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(path.open('rb'), content_type='image/jpeg')
        response['Cache-Control'] = 'private, max-age=86400'
        return response


class AudioMetaView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = AudioTrack.objects.all()
        folder = request.query_params.get('folder')
        parent = request.query_params.get('parent')
        if folder:
            qs = qs.filter(folder_slug=folder)
        parent_rows = (
            qs.exclude(parent='')
            .values('parent')
            .annotate(track_count=Count('id'))
        )
        top_counts = {}
        for row in parent_rows:
            top = row['parent'].split('/')[0]
            top_counts[top] = top_counts.get(top, 0) + row['track_count']
        parents = [
            {'name': name, 'track_count': top_counts[name]}
            for name in sorted(top_counts)
        ]
        if parent:
            qs = qs.filter(Q(parent=parent) | Q(parent__startswith=f'{parent}/'))
        roots = [
            {
                'slug': row['slug'],
                'label': row.get('label') or row['slug'],
                'track_count': AudioTrack.objects.filter(folder_slug=row['slug']).count(),
                'available': Path(row['path']).is_dir(),
            }
            for row in configured_roots()
        ]
        return Response({
            'folders': roots,
            'artists': list(
                qs.exclude(artist='').order_by('artist').values_list('artist', flat=True).distinct()[:200]
            ),
            'composers': list(
                qs.exclude(composer='').order_by('composer').values_list('composer', flat=True).distinct()[:200]
            ),
            'genres': list(
                qs.exclude(genre='').order_by('genre').values_list('genre', flat=True).distinct()[:200]
            ),
            'albums': list(
                qs.exclude(album='').order_by('album').values_list('album', flat=True).distinct()[:200]
            ),
            'years': list(
                qs.exclude(year__isnull=True).order_by('-year').values_list('year', flat=True).distinct()[:200]
            ),
            'parents': parents,
            'track_count': qs.count(),
        })


class AudioReindexView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsSuperuserRole]

    def post(self, request):
        return Response(index_roots())
