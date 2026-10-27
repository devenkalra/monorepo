import logging

from django.conf import settings
from django.http import FileResponse
from django.db.models import Count
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import entities, google_auth
from .engine import WriteGuard, open_list
from .engine.errors import ConfigError
from .models import ContactsState, GoogleAccount, ReviewItem, SourceFile, SyncRun
from .pages import PAGE_SLUG
from .permissions import IsSuperuserRole
from .runner import (CHECK_KEY, IGNORE_KEY, SYNC_TOKEN_KEY, ApplyRefused, active_run, check_import_targets,
                     clickup_config, create_live_from_plan, data_dir, orgs_list_id, save_upload, writes_enabled)
from .serializers import (ChangeLogSerializer, ReviewItemSerializer, SourceFileSerializer, SyncRunDetailSerializer,
                          SyncRunSerializer)

logger = logging.getLogger(__name__)

OPTION_SPECS = {
    'google': {'full': bool, 'photos': bool, 'writeback': bool, 'rename_tasks': bool, 'overwrite_values': bool,
               'ignore_labels': list},
    'linkedin': {'overwrite_values': bool},
    'whatsapp': {'no_create': bool, 'only_saved': bool, 'trust_exact_names': bool, 'overwrite_values': bool},
    'export': {},
    'import': {'people_list_id': str, 'orgs_list_id': str},
    'merge': {'survivor': str, 'loser': str},
}
FILE_SLOTS = {
    'linkedin': {'connections': (SourceFile.Kind.LINKEDIN_CONNECTIONS, True),
                 'messages': (SourceFile.Kind.LINKEDIN_MESSAGES, False)},
    'whatsapp': {'export': (SourceFile.Kind.WHATSAPP, True)},
    'import': {'export': (SourceFile.Kind.CONTACTS_EXPORT, True)},
}
SYNC_SOURCES = ('google', 'linkedin', 'whatsapp')


def _who(request):
    return getattr(request.user, 'email', '') or getattr(request.user, 'username', '') or ''


class SuperuserMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]


class StatusView(SuperuserMixin, APIView):
    def get(self, request):
        token, list_id = clickup_config()
        account = GoogleAccount.objects.order_by('id').first()
        latest = {}
        for source in SYNC_SOURCES:
            for mode in SyncRun.Mode.values:
                run = SyncRun.objects.filter(source=source, mode=mode).first()
                latest.setdefault(source, {})[mode] = SyncRunSerializer(run).data if run else None
        pending = dict(ReviewItem.objects.filter(decision=ReviewItem.Decision.PENDING)
                       .values_list('source').annotate(n=Count('id')))
        run = active_run()
        return Response({
            'clickup': {'configured': bool(token and list_id), 'list_id': list_id, 'orgs_list_id': orgs_list_id(),
                        'writes_enabled': writes_enabled()},
            'google': {
                'connected': bool(account and account.refresh_token),
                'email': account.email if account else '',
                'can_write': bool(account and account.can_write),
                'last_error': account.last_error if account else '',
                'has_sync_token': bool(ContactsState.get(SYNC_TOKEN_KEY)),
            },
            'last_check': ContactsState.get(CHECK_KEY),
            'pending_reviews': pending,
            'active_run': SyncRunSerializer(run).data if run else None,
            'latest': latest,
            'ignore_labels': ContactsState.get(IGNORE_KEY, []),
            'plan_max_age_hours': float(getattr(settings, 'CONTACTS_PLAN_MAX_AGE_HOURS', 24)),
        })


class CheckView(SuperuserMixin, APIView):
    """Read the list's custom fields and report what the sync needs (read-only)."""

    def post(self, request):
        token, list_id = clickup_config()
        try:
            cu, missing = open_list(token, list_id, WriteGuard(dry=True))
            report = cu.field_report(missing)
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        except Exception as e:  # noqa: BLE001
            return Response({'detail': f'ClickUp check failed: {e}'}, status=502)
        report['checked_at'] = timezone.now().isoformat()
        ContactsState.put(CHECK_KEY, report)
        return Response(report)


class SettingsView(SuperuserMixin, APIView):
    def put(self, request):
        labels = request.data.get('ignore_labels', [])
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            return Response({'detail': 'ignore_labels must be a list of strings.'}, status=400)
        cleaned = sorted({x.strip() for x in labels if x.strip()})
        ContactsState.put(IGNORE_KEY, cleaned)
        return Response({'ignore_labels': cleaned})


class GoogleOAuthStartView(SuperuserMixin, APIView):
    def get(self, request):
        write = request.query_params.get('write') in ('1', 'true')
        try:
            url = google_auth.authorize_url(request, write=write)
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'authorize_url': url, 'redirect_uri': google_auth.redirect_uri(request)})


class GoogleOAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        frontend = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/') or \
            request.build_absolute_uri('/').rstrip('/')
        if not google_auth.consume_state(request.query_params.get('state')):
            return Response({'detail': 'Invalid or expired sign-in attempt; start again from the app.'}, status=400)
        if request.query_params.get('error'):
            return redirect(f'{frontend}/p/{PAGE_SLUG}?google=denied')
        code = request.query_params.get('code')
        if not code:
            return Response({'detail': 'Missing code'}, status=400)
        try:
            google_auth.connect(code, request)
        except Exception as e:  # noqa: BLE001
            logger.warning('Contacts Google connect failed: %s', e)
            return Response({'detail': f'Google connection failed: {e}'}, status=400)
        return redirect(f'{frontend}/p/{PAGE_SLUG}?google=connected')


class GoogleDisconnectView(SuperuserMixin, APIView):
    def post(self, request):
        GoogleAccount.objects.all().delete()
        return Response({'detail': 'Disconnected.'})


class UploadView(SuperuserMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return Response(SourceFileSerializer(SourceFile.objects.all()[:30], many=True).data)

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'Choose a file.'}, status=400)
        try:
            sf = save_upload(request.data.get('kind', ''), upload)
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(SourceFileSerializer(sf).data, status=201)


def _clean_options(source, raw):
    spec = OPTION_SPECS[source]
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ConfigError('options must be an object.')
    unknown = set(raw) - set(spec)
    if unknown:
        raise ConfigError(f"Unknown options for {source}: {', '.join(sorted(unknown))}")
    out = {}
    for name, kind in spec.items():
        if name not in raw:
            continue
        val = raw[name]
        if kind is bool:
            if not isinstance(val, bool):
                raise ConfigError(f'{name} must be true or false.')
        elif kind is str:
            if not isinstance(val, str):
                raise ConfigError(f'{name} must be text.')
            val = val.strip()
        elif not (isinstance(val, list) and all(isinstance(x, str) for x in val)):
            raise ConfigError(f'{name} must be a list of strings.')
        out[name] = val
    if source == 'import':
        return out
    if source == 'merge':
        if not out.get('survivor') or not out.get('loser'):
            raise ConfigError('Choose the record to keep and the record to merge into it.')
        if out['survivor'] == out['loser']:
            raise ConfigError('A record can\'t be merged into itself.')
        return out
    if source == 'export':
        return {'people_list_id': clickup_config()[1], 'orgs_list_id': orgs_list_id()}
    out.setdefault('overwrite_values', True)
    if source == 'google':
        out.setdefault('rename_tasks', False)
        if 'ignore_labels' not in out:
            out['ignore_labels'] = ContactsState.get(IGNORE_KEY, [])
    return out


def _clean_files(source, raw):
    slots = FILE_SLOTS.get(source, {})
    raw = raw or {}
    chosen = []
    for slot, (kind, required) in slots.items():
        fid = raw.get(slot)
        if not fid:
            if required:
                raise ConfigError(f'Upload the {SourceFile.Kind(kind).label} file first.')
            continue
        sf = SourceFile.objects.filter(pk=fid, kind=kind).first()
        if not sf:
            raise ConfigError(f'Unknown {SourceFile.Kind(kind).label} file #{fid}.')
        chosen.append(sf)
    return chosen


class SyncRunViewSet(SuperuserMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = SyncRun.objects.prefetch_related('files', 'applied_by')

    def get_serializer_class(self):
        return SyncRunDetailSerializer if self.action == 'retrieve' else SyncRunSerializer

    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get('source'):
            qs = qs.filter(source=request.query_params['source'])
        return Response(SyncRunSerializer(qs[:50], many=True).data)

    def create(self, request):
        """Start a dry run (preview). Live runs are only created by applying a preview."""
        source = request.data.get('source')
        if source not in OPTION_SPECS:
            return Response({'detail': 'source must be google, linkedin, whatsapp, merge, export or import.'},
                            status=400)
        try:
            options = _clean_options(source, request.data.get('options'))
            files = _clean_files(source, request.data.get('files'))
            if source == 'export' and not options['people_list_id']:
                raise ConfigError('Set CONTACTS_CLICKUP_LIST_ID on the server first.')
            if source == 'import':
                check_import_targets(options, files[0])
            if source == 'google':
                account = GoogleAccount.objects.order_by('id').first()
                if not account or not account.refresh_token:
                    raise ConfigError('Connect Google first.')
                if options.get('writeback') and not account.can_write:
                    raise ConfigError('Writeback needs write access to Google Contacts; grant it first.')
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        if active_run():
            return Response({'detail': 'Another run is queued or running.'}, status=409)
        run = SyncRun.objects.create(source=source, mode=SyncRun.Mode.DRY, options=options, created_by=_who(request))
        run.files.set(files)
        return Response(SyncRunSerializer(run).data, status=201)

    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        plan = self.get_object()
        try:
            live = create_live_from_plan(plan, user=_who(request))
        except ApplyRefused as e:
            return Response({'detail': str(e)}, status=409)
        return Response(SyncRunSerializer(live).data, status=201)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        run = self.get_object()
        if run.status == SyncRun.Status.QUEUED:
            SyncRun.objects.filter(pk=run.pk, status=SyncRun.Status.QUEUED).update(
                status=SyncRun.Status.CANCELLED, finished_at=timezone.now(), error='Cancelled before it started.')
        elif run.status == SyncRun.Status.RUNNING:
            SyncRun.objects.filter(pk=run.pk).update(cancel_requested=True)
        run.refresh_from_db()
        return Response(SyncRunSerializer(run).data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        run = self.get_object()
        path = data_dir() / run.output.path if run.output else None
        if not path or not path.exists():
            return Response({'detail': 'This run has no file to download.'}, status=404)
        return FileResponse(path.open('rb'), as_attachment=True, filename=run.output.original_name,
                            content_type='application/json')

    @action(detail=True, methods=['get'])
    def changes(self, request, pk=None):
        run = self.get_object()
        return Response(ChangeLogSerializer(run.changes.all()[:5000], many=True).data)


class ReviewItemViewSet(SuperuserMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ReviewItemSerializer

    def get_queryset(self):
        qs = ReviewItem.objects.all()
        if self.request.query_params.get('decision'):
            qs = qs.filter(decision=self.request.query_params['decision'])
        if self.request.query_params.get('source'):
            qs = qs.filter(source=self.request.query_params['source'])
        return qs

    @action(detail=True, methods=['post'])
    def decide(self, request, pk=None):
        item = ReviewItem.objects.filter(pk=pk).first()
        if not item:
            return Response({'detail': 'Not found.'}, status=404)
        decision = request.data.get('decision')
        if decision not in ReviewItem.Decision.values:
            return Response({'detail': 'decision must be same, new or pending.'}, status=400)
        item.decision = decision
        item.chosen_task_id = str(request.data.get('task_id') or '')[:64] if decision == 'same' else ''
        item.decided_by = _who(request)
        item.decided_at = timezone.now()
        item.save(update_fields=['decision', 'chosen_task_id', 'decided_by', 'decided_at', 'updated_at'])
        return Response(ReviewItemSerializer(item).data)


class EntityListView(SuperuserMixin, APIView):
    """GET: the People & Orgs list from the local copy. POST: re-read it from ClickUp (read-only)."""

    def get(self, request):
        try:
            return Response(entities.listing())
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)

    def post(self, request):
        try:
            return Response(entities.refresh())
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        except RuntimeError as e:
            logger.exception('Entity refresh failed')
            return Response({'detail': str(e)}, status=502)


class EntityDetailView(SuperuserMixin, APIView):
    def get(self, request, task_id):
        try:
            return Response(entities.detail(task_id))
        except entities.EditError as e:
            return Response({'detail': str(e)}, status=e.status)
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        except RuntimeError as e:
            return Response({'detail': str(e)}, status=502)

    def put(self, request, task_id):
        if not isinstance(request.data, dict):
            return Response({'detail': 'Expected a JSON object.'}, status=400)
        try:
            return Response(entities.save(task_id, request.data, user=_who(request)))
        except entities.EditError as e:
            return Response({'detail': str(e)}, status=e.status)
        except ConfigError as e:
            return Response({'detail': str(e)}, status=400)
        except RuntimeError as e:
            logger.exception('Entity save failed')
            return Response({'detail': str(e)}, status=502)
