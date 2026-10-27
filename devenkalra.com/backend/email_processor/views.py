import logging

from django.conf import settings
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .command_center import (
    apply_selection_action,
    get_active_session,
    handle_command,
    purge_expired_sessions,
    serialize_session,
)
from .models import CommandSession, EmailJob, EmailMessage, MailboxAccount, SavedSearch, WorkflowRun
from .permissions import IsSuperuserRole
from .serializers import (
    EmailMessageSerializer,
    MailboxAccountSerializer,
    SavedSearchSerializer,
    WorkflowRunSerializer,
)
from .sync import (
    enqueue_job,
    execute_workflow_for_message,
    get_active_mailbox,
    reconcile_mailbox,
    renew_watch,
    service_for,
)

logger = logging.getLogger(__name__)


class SuperuserAuthMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]


class MailboxViewSet(SuperuserAuthMixin, viewsets.ReadOnlyModelViewSet):
    queryset = MailboxAccount.objects.all()
    serializer_class = MailboxAccountSerializer

    @action(detail=False, methods=['get'])
    def status(self, request):
        mailbox = get_active_mailbox()
        pending_jobs = EmailJob.objects.filter(status=EmailJob.Status.PENDING).count()
        review_count = EmailMessage.objects.filter(status=EmailMessage.Status.NEEDS_REVIEW).count()
        data = {
            'mailbox': MailboxAccountSerializer(mailbox).data if mailbox else None,
            'pending_jobs': pending_jobs,
            'needs_review': review_count,
            'worker_enabled': getattr(settings, 'EMAIL_WORKER_ENABLED', True),
        }
        return Response(data)

    @action(detail=False, methods=['post'])
    def sync_now(self, request):
        mailbox = get_active_mailbox()
        if not mailbox:
            return Response({'detail': 'Connect Gmail first.'}, status=400)
        enqueue_job(EmailJob.JobType.RECONCILE, mailbox=mailbox)
        return Response({'detail': 'Reconcile job enqueued.'})

    @action(detail=False, methods=['post'])
    def renew_watch(self, request):
        try:
            result = renew_watch()
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'detail': 'Watch renewed.', 'result': result})


class EmailMessageViewSet(SuperuserAuthMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = EmailMessageSerializer

    def get_queryset(self):
        qs = EmailMessage.objects.select_related('classification').prefetch_related('runs')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def _apply_intent(self, message, intent):
        if not intent or not hasattr(message, 'classification'):
            return
        message.classification.intent = intent
        message.classification.raw = {
            **(message.classification.raw or {}),
            'intent': intent,
        }
        message.classification.save(update_fields=['intent', 'raw'])

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        message = self.get_object()
        self._apply_intent(message, request.data.get('intent'))
        try:
            run = execute_workflow_for_message(message)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({
            'message': EmailMessageSerializer(message).data,
            'run': WorkflowRunSerializer(run).data,
        })

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        message = self.get_object()
        try:
            execute_workflow_for_message(message, kind='ignore')
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        message.refresh_from_db()
        return Response(EmailMessageSerializer(message).data)

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """Bulk ops on Needs-review (and other) messages; Gmail ops use thread_id."""
        from . import gmail as gmail_api

        action = (request.data.get('action') or '').strip().lower()
        ids = request.data.get('ids') or []
        intent = request.data.get('intent')
        label_id = request.data.get('label_id') or None
        label_name = request.data.get('label_name') or None
        confirm = bool(request.data.get('confirm'))

        if not isinstance(ids, list) or not ids:
            return Response({'detail': 'ids must be a non-empty list.'}, status=400)

        messages = list(
            EmailMessage.objects.select_related('classification', 'mailbox')
            .filter(id__in=ids)
        )
        if not messages:
            return Response({'detail': 'No matching messages.'}, status=400)

        allowed = {
            'approve', 'dismiss', 'archive', 'trash', 'label', 'label_processed',
        }
        if action not in allowed:
            return Response({'detail': f'Unsupported action: {action}'}, status=400)

        thread_ids = list(dict.fromkeys(
            [m.thread_id for m in messages if m.thread_id]
        ))

        # Gmail-side thread actions
        if action in ('archive', 'trash', 'label', 'label_processed'):
            if action == 'label' and not (label_id or label_name):
                return Response({'detail': 'label_id or label_name required.'}, status=400)
            if not thread_ids:
                return Response({'detail': 'Selected messages have no thread_id.'}, status=400)
            if action == 'trash' and not confirm:
                return Response({
                    'type': 'confirm',
                    'action': action,
                    'ids': [m.id for m in messages],
                    'thread_ids': thread_ids,
                    'target_count': len(thread_ids),
                    'detail': (
                        f'Confirm trash on {len(thread_ids)} thread(s). '
                        'Resubmit with confirm=true.'
                    ),
                })
            mailbox = get_active_mailbox()
            if not mailbox or not mailbox.refresh_token:
                return Response({'detail': 'Connect Gmail first.'}, status=400)
            try:
                result = gmail_api.batch_thread_action(
                    service_for(mailbox),
                    thread_ids,
                    action,
                    label_id=label_id,
                    label_name=label_name,
                )
            except Exception as exc:
                logger.exception('Bulk Gmail action failed')
                return Response({'detail': str(exc)}, status=400)

            # Mirror dismiss/archive into local status when leaving inbox
            if action in ('archive', 'trash', 'label_processed'):
                for message in messages:
                    if action == 'trash':
                        message.status = EmailMessage.Status.IGNORED
                    elif message.status == EmailMessage.Status.NEEDS_REVIEW:
                        message.status = EmailMessage.Status.IGNORED
                    message.save(update_fields=['status', 'updated_at'])

            return Response({
                'type': 'action',
                'action': action,
                'affected': result.get('affected', 0),
                'ids': [m.id for m in messages],
                'thread_ids': thread_ids,
                'result': result,
            })

        # Workflow actions (approve / dismiss)
        succeeded = []
        failed = []
        for message in messages:
            try:
                if action == 'approve':
                    self._apply_intent(message, intent)
                    run = execute_workflow_for_message(message)
                    succeeded.append({
                        'id': message.id,
                        'run_id': getattr(run, 'pk', None),
                        'status': message.status,
                    })
                else:  # dismiss
                    execute_workflow_for_message(message, kind='ignore')
                    message.refresh_from_db()
                    succeeded.append({'id': message.id, 'status': message.status})
            except Exception as exc:
                failed.append({'id': message.id, 'error': str(exc)[:500]})

        return Response({
            'type': 'action',
            'action': action,
            'intent': intent,
            'succeeded': succeeded,
            'failed': failed,
            'affected': len(succeeded),
            'ids': [m.id for m in messages],
            'thread_ids': thread_ids,
        })


class WorkflowRunViewSet(SuperuserAuthMixin, viewsets.ReadOnlyModelViewSet):
    queryset = WorkflowRun.objects.select_related('message').all()
    serializer_class = WorkflowRunSerializer


class SavedSearchViewSet(SuperuserAuthMixin, viewsets.ModelViewSet):
    """Persisted Command Center searches (shared across browsers/devices)."""
    serializer_class = SavedSearchSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return SavedSearch.objects.filter(user_id=self.request.user.id)

    def create(self, request, *args, **kwargs):
        prompt = (request.data.get('prompt') or '').strip()
        gmail_query = (request.data.get('gmail_query') or '').strip()
        label = (request.data.get('label') or '').strip()[:120]
        if not prompt and not gmail_query:
            return Response({'detail': 'prompt or gmail_query is required.'}, status=400)
        prompt = prompt or gmail_query
        if not label:
            label = prompt[:120]
        existing = SavedSearch.objects.filter(
            user_id=request.user.id,
            prompt=prompt,
            gmail_query=gmail_query,
        ).first()
        if existing:
            existing.label = label
            existing.save(update_fields=['label', 'updated_at'])
            return Response(SavedSearchSerializer(existing).data)
        obj = SavedSearch.objects.create(
            user_id=request.user.id,
            label=label,
            prompt=prompt,
            gmail_query=gmail_query,
        )
        # Keep a reasonable history size per user
        ids = list(
            SavedSearch.objects.filter(user_id=request.user.id)
            .order_by('-updated_at', '-id')
            .values_list('id', flat=True)[40:]
        )
        if ids:
            SavedSearch.objects.filter(id__in=ids).delete()
        return Response(SavedSearchSerializer(obj).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        if 'label' in request.data:
            obj.label = (request.data.get('label') or '').strip()[:120]
        obj.save(update_fields=['label', 'updated_at'])
        return Response(SavedSearchSerializer(obj).data)


class CommandCenterView(SuperuserAuthMixin, APIView):
    """PRD §5 Interactive Command Center — Prompt-to-Select + batch actions."""

    def get(self, request):
        from . import gmail as gmail_api
        purge_expired_sessions()
        session = get_active_session(request.user.id)
        labels = []
        mailbox = get_active_mailbox()
        if mailbox and mailbox.refresh_token:
            try:
                labels = gmail_api.list_user_labels(service_for(mailbox))
            except Exception as exc:
                logger.warning('Failed to list labels: %s', exc)
        return Response({
            'session': serialize_session(session),
            'labels': labels,
            'examples': [
                'Find all newsletters from today',
                'Show unread promotions from this week',
                'Archive all except 3 and 5',
                'Trash 1, 2, and 4',
                'Mark all as read',
            ],
        })

    def post(self, request):
        prompt = (request.data.get('prompt') or '').strip()
        confirm = bool(request.data.get('confirm'))
        force_search = bool(request.data.get('force_search'))
        try:
            result = handle_command(
                request.user.id,
                prompt,
                confirm=confirm,
                force_search=force_search,
            )
        except Exception as exc:
            logger.exception('Command center failed')
            return Response({'detail': str(exc)}, status=400)
        return Response(result)

    def delete(self, request):
        deleted, _ = CommandSession.objects.filter(user_id=request.user.id).delete()
        return Response({'detail': 'Session cleared.', 'deleted': deleted})


class CommandSelectionView(SuperuserAuthMixin, APIView):
    """Deterministic selection actions using Gmail thread ids from the active list."""

    def post(self, request):
        action = (request.data.get('action') or '').strip()
        thread_ids = request.data.get('thread_ids') or []
        gmail_ids = request.data.get('gmail_ids') or []
        label_id = request.data.get('label_id') or None
        label_name = request.data.get('label_name') or None
        confirm = bool(request.data.get('confirm'))
        if not isinstance(thread_ids, list):
            return Response({'detail': 'thread_ids must be a list.'}, status=400)
        if not isinstance(gmail_ids, list):
            return Response({'detail': 'gmail_ids must be a list.'}, status=400)
        try:
            result = apply_selection_action(
                request.user.id,
                action=action,
                thread_ids=thread_ids,
                gmail_ids=gmail_ids,
                label_id=label_id,
                label_name=label_name,
                confirm=confirm,
            )
        except Exception as exc:
            logger.exception('Selection action failed')
            return Response({'detail': str(exc)}, status=400)
        return Response(result)


class GmailOAuthStartView(SuperuserAuthMixin, APIView):
    def get(self, request):
        from .gmail import oauth_authorize_url
        redirect_uri = request.build_absolute_uri('/api/email/oauth/callback/')
        # Prefer configured public URL if behind proxy
        public = getattr(settings, 'EMAIL_OAUTH_REDIRECT_URI', '') or ''
        if public:
            redirect_uri = public
        url = oauth_authorize_url(redirect_uri, state='email-processor')
        return Response({'authorize_url': url, 'redirect_uri': redirect_uri})


@method_decorator(csrf_exempt, name='dispatch')
class GmailOAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from .gmail import (
            build_gmail_service,
            ensure_label,
            exchange_code,
            get_profile_email,
            LABEL_NEEDS_REVIEW,
            LABEL_PROCESSED,
        )

        error = request.query_params.get('error')
        if error:
            return Response({'detail': error}, status=400)
        code = request.query_params.get('code')
        if not code:
            return Response({'detail': 'Missing code'}, status=400)

        redirect_uri = getattr(settings, 'EMAIL_OAUTH_REDIRECT_URI', '') or \
            request.build_absolute_uri('/api/email/oauth/callback/')
        try:
            tokens = exchange_code(code, redirect_uri)
        except Exception as exc:
            return Response({'detail': f'Token exchange failed: {exc}'}, status=400)

        refresh = tokens.get('refresh_token')
        if not refresh:
            # May happen if previously consented without prompt=consent
            return Response({
                'detail': 'No refresh_token returned. Revoke app access in Google Account and retry.',
            }, status=400)

        service = build_gmail_service(refresh)
        email = get_profile_email(service)
        ensure_label(service, LABEL_PROCESSED)
        ensure_label(service, LABEL_NEEDS_REVIEW)

        mailbox, _ = MailboxAccount.objects.update_or_create(
            email=email,
            defaults={
                'refresh_token': refresh,
                'is_active': True,
                'last_error': '',
            },
        )
        # Deactivate other mailboxes (single-user)
        MailboxAccount.objects.exclude(pk=mailbox.pk).update(is_active=False)

        try:
            renew_watch(mailbox)
        except Exception as exc:
            mailbox.last_error = f'Connected but watch failed: {exc}'
            mailbox.save(update_fields=['last_error'])

        enqueue_job(EmailJob.JobType.RECONCILE, mailbox=mailbox)

        frontend = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        if not frontend:
            # Prefer same host as the OAuth callback (local docker :8090, prod, etc.)
            frontend = request.build_absolute_uri('/').rstrip('/')
        return redirect(f'{frontend}/p/email-processor?gmail=connected')


@method_decorator(csrf_exempt, name='dispatch')
class PubSubPushView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # Optional shared token: Authorization: Bearer <EMAIL_PUBSUB_VERIFICATION_TOKEN>
        expected = getattr(settings, 'EMAIL_PUBSUB_VERIFICATION_TOKEN', '') or ''
        if expected:
            auth = request.headers.get('Authorization', '')
            if auth != f'Bearer {expected}' and request.query_params.get('token') != expected:
                return Response({'detail': 'Unauthorized'}, status=401)

        mailbox = get_active_mailbox()
        if not mailbox:
            return Response({'detail': 'No mailbox'}, status=200)

        # Avoid stampeding: coalesce pending reconcile jobs
        if not EmailJob.objects.filter(
            mailbox=mailbox,
            job_type=EmailJob.JobType.RECONCILE,
            status__in=[EmailJob.Status.PENDING, EmailJob.Status.RUNNING],
        ).exists():
            enqueue_job(EmailJob.JobType.RECONCILE, mailbox=mailbox)
        return Response({'ok': True})
