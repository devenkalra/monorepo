"""Gmail Assistant API views."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from celery.result import AsyncResult
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import gmail_api
from .models import EmailSummary, GmailAccount, LlmJob, SavedPrompt, SummarizeSchedule
from .nl_query import nl_to_gmail_query
from .serializers import (
    GmailAccountSerializer,
    SavedPromptSerializer,
    SummarizeScheduleSerializer,
    UserPreferenceSerializer,
)
from .services import (
    get_active_account,
    get_or_create_prefs,
    scrub_zero_knowledge_data,
    set_active_account,
)
from .tasks import process_emails_task, run_summarize_schedule, summarize_emails_task

logger = logging.getLogger(__name__)

OAUTH_STATE_SALT = 'gmail-assistant-oauth'


def _account_from_request(request) -> GmailAccount | None:
    account_id = (
        request.query_params.get('account_id')
        or request.data.get('account_id')
        or request.headers.get('X-Gmail-Account-Id')
    )
    return get_active_account(request.user, account_id)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def status_view(request):
    prefs = get_or_create_prefs(request.user)
    accounts = GmailAccount.objects.filter(user=request.user)
    active = accounts.filter(is_active=True).first() or accounts.first()
    return Response(
        {
            'connected': accounts.exists(),
            'active_account_id': str(active.id) if active else None,
            'accounts': GmailAccountSerializer(accounts, many=True).data,
            'preferences': UserPreferenceSerializer(prefs).data,
            'ui': '/gmail-app/',
            'oauth_start': '/api/gmail/oauth/start/',
        }
    )


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    prefs = get_or_create_prefs(request.user)
    if request.method == 'GET':
        return Response(UserPreferenceSerializer(prefs).data)

    enabling_zk = (
        'zero_knowledge' in request.data
        and bool(request.data.get('zero_knowledge'))
        and not prefs.zero_knowledge
    )
    if enabling_zk and not request.data.get('confirm_scrub'):
        return Response(
            {
                'detail': (
                    'Turning on zero-knowledge permanently deletes stored summaries '
                    'and process results for your account. Retry with confirm_scrub=true.'
                ),
                'requires_confirm_scrub': True,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    ser = UserPreferenceSerializer(prefs, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()

    scrub_stats = None
    if enabling_zk:
        scrub_stats = scrub_zero_knowledge_data(request.user)
        logger.info(
            'ZK enabled for user=%s scrub=%s',
            request.user.id,
            scrub_stats,
        )

    payload = dict(ser.data)
    if scrub_stats is not None:
        payload['scrubbed'] = scrub_stats
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def accounts_list(request):
    accounts = GmailAccount.objects.filter(user=request.user)
    return Response({'accounts': GmailAccountSerializer(accounts, many=True).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def account_activate(request, account_id):
    account = get_object_or_404(GmailAccount, id=account_id, user=request.user)
    set_active_account(request.user, account)
    return Response(GmailAccountSerializer(account).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def account_disconnect(request, account_id):
    account = get_object_or_404(GmailAccount, id=account_id, user=request.user)
    was_active = account.is_active
    account.delete()
    if was_active:
        nxt = GmailAccount.objects.filter(user=request.user).first()
        if nxt:
            set_active_account(request.user, nxt)
    return Response({'ok': True, 'id': str(account_id)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def oauth_start(request):
    state = signing.dumps(
        {'uid': request.user.id, 'nonce': secrets.token_urlsafe(8)},
        salt=OAUTH_STATE_SALT,
    )
    url = gmail_api.oauth_authorize_url(state=state)
    return Response({'authorize_url': url})


def _gmail_ui_redirect(query: str) -> HttpResponseRedirect:
    """Send browser back to the SPA after OAuth (Vite origin locally)."""
    origin = (getattr(settings, 'GMAIL_UI_ORIGIN', '') or '').rstrip('/')
    path = f'/gmail-app/?{query}' if query else '/gmail-app/'
    return HttpResponseRedirect(f'{origin}{path}' if origin else path)


@api_view(['GET'])
@permission_classes([AllowAny])
def oauth_callback(request):
    """Google redirects here (may be unauthenticated browser)."""
    error = request.query_params.get('error')
    if error:
        return _gmail_ui_redirect(f'oauth=error&detail={quote(error)}')
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    if not code or not state:
        return _gmail_ui_redirect('oauth=error&detail=missing_code')
    try:
        payload = signing.loads(state, salt=OAUTH_STATE_SALT, max_age=600)
        user_id = payload['uid']
    except Exception:  # noqa: BLE001
        return _gmail_ui_redirect('oauth=error&detail=bad_state')

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return _gmail_ui_redirect('oauth=error&detail=user')

    try:
        token = gmail_api.exchange_code(code)
        refresh = token.get('refresh_token')
        if not refresh:
            return _gmail_ui_redirect('oauth=error&detail=no_refresh_token')
        service = gmail_api.build_gmail_service(refresh)
        email = gmail_api.get_profile_email(service)
        account, created = GmailAccount.objects.update_or_create(
            user=user,
            email=email,
            defaults={
                'refresh_token': refresh,
                'scopes': ' '.join(gmail_api.GMAIL_SCOPES),
                'last_error': '',
            },
        )
        if created or not GmailAccount.objects.filter(user=user, is_active=True).exists():
            set_active_account(user, account)
    except Exception as exc:  # noqa: BLE001
        logger.exception('Gmail OAuth failed')
        return _gmail_ui_redirect(f'oauth=error&detail={quote(str(exc)[:160])}')
    return _gmail_ui_redirect('oauth=ok')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def query_preview(request):
    try:
        result = nl_to_gmail_query(
            request.data.get('prompt') or '',
            start_date=request.data.get('start_date'),
            end_date=request.data.get('end_date'),
            days=request.data.get('days'),
            keyword=request.data.get('keyword'),
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search(request):
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    prompt = request.data.get('prompt') or ''
    start_date = request.data.get('start_date')
    end_date = request.data.get('end_date')
    days = request.data.get('days')
    keyword = request.data.get('keyword')
    max_results = int(request.data.get('max_results') or 100)
    if not any(
        [
            (prompt or '').strip(),
            start_date,
            end_date,
            days is not None and str(days) != '',
            (keyword or '').strip(),
        ]
    ):
        return Response(
            {'detail': 'Enter a prompt and/or search qualifiers.'}, status=400
        )
    try:
        parsed = nl_to_gmail_query(
            prompt,
            start_date=start_date,
            end_date=end_date,
            days=days,
            keyword=keyword,
        )
        service = gmail_api.build_gmail_service(account.refresh_token)
        ids = gmail_api.list_message_ids(
            service, query=parsed['query'], max_results=max_results
        )
    except Exception as exc:  # noqa: BLE001
        account.last_error = str(exc)[:500]
        account.save(update_fields=['last_error', 'updated_at'])
        return Response({'detail': str(exc)}, status=400)

    prefs = get_or_create_prefs(request.user)
    summaries = {
        s.gmail_id: s
        for s in EmailSummary.objects.filter(account=account, gmail_id__in=ids)
    }
    emails = []
    for gid in ids:
        meta = gmail_api.fetch_message_metadata(service, gid)
        row = summaries.get(gid)
        # has_summary means "summary text is available to show".
        # In ZK that text is browser-local only — never claim true from DB category.
        has_summary = False
        if row and not prefs.zero_knowledge:
            has_summary = bool((row.brief_summary or '').strip())
        meta['has_summary'] = has_summary
        if row and not prefs.zero_knowledge:
            meta['brief_summary'] = row.brief_summary
            meta['key_points'] = row.key_points
            meta['details'] = row.details
            meta['category'] = row.category
            meta['category_confidence'] = row.category_confidence
        elif row and prefs.zero_knowledge:
            meta['category'] = row.category
            meta['category_confidence'] = row.category_confidence
            meta['brief_summary'] = ''
            meta['key_points'] = []
            meta['details'] = ''
            meta['has_category'] = bool(row.category)
        else:
            meta['brief_summary'] = ''
            meta['key_points'] = []
            meta['details'] = ''
            meta['category'] = ''
            meta['category_confidence'] = 0
            meta['has_category'] = False
        emails.append(meta)

    emails.sort(key=lambda m: int(m.get('internal_date_ms') or 0), reverse=True)
    return Response(
        {
            'prompt': prompt,
            'query': parsed['query'],
            'notes': parsed.get('notes') or [],
            'count': len(emails),
            'emails': emails,
            'account_id': str(account.id),
            'zero_knowledge': prefs.zero_knowledge,
        }
    )


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def prompts_view(request):
    if request.method == 'GET':
        rows = SavedPrompt.objects.filter(user=request.user)
        return Response({'prompts': SavedPromptSerializer(rows, many=True).data})
    ser = SavedPromptSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    label = ser.validated_data['label'].strip()
    prompt = ser.validated_data['prompt'].strip()
    obj, _ = SavedPrompt.objects.update_or_create(
        user=request.user,
        label=label,
        defaults={'prompt': prompt},
    )
    return Response({'prompt': SavedPromptSerializer(obj).data})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def prompt_delete(request, prompt_id):
    deleted, _ = SavedPrompt.objects.filter(user=request.user, id=prompt_id).delete()
    if not deleted:
        return Response({'detail': 'Not found'}, status=404)
    return Response({'ok': True, 'id': str(prompt_id)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def labels_view(request):
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    try:
        service = gmail_api.build_gmail_service(account.refresh_token)
        labels = gmail_api.list_labels(service)
    except Exception as exc:  # noqa: BLE001
        return Response({'detail': str(exc)}, status=400)
    return Response({'labels': labels})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def email_detail(request, gmail_id):
    """Full message body for the detail pane (live from Gmail; not persisted)."""
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    gid = (gmail_id or '').strip()
    if not gid:
        return Response({'detail': 'gmail_id required'}, status=400)
    try:
        service = gmail_api.build_gmail_service(account.refresh_token)
        message = gmail_api.fetch_message(service, gid)
    except Exception as exc:  # noqa: BLE001
        logger.exception('email_detail failed for %s', gid)
        return Response({'detail': str(exc)}, status=400)

    prefs = get_or_create_prefs(request.user)
    row = EmailSummary.objects.filter(account=account, gmail_id=gid).first()
    if row:
        message['category'] = row.category
        message['category_confidence'] = row.category_confidence
        if prefs.zero_knowledge:
            # Summary text lives in the browser only.
            message['has_summary'] = False
            message['has_category'] = bool(row.category)
            message['brief_summary'] = ''
            message['key_points'] = []
            message['details'] = ''
        else:
            message['has_summary'] = bool((row.brief_summary or '').strip())
            message['brief_summary'] = row.brief_summary
            message['key_points'] = row.key_points
            message['details'] = row.details
    else:
        message['has_summary'] = False
        message['has_category'] = False
        message['category'] = ''
        message['category_confidence'] = 0
        message['brief_summary'] = ''
        message['key_points'] = []
        message['details'] = ''
    return Response({'email': message, 'zero_knowledge': prefs.zero_knowledge})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_action(request):
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    action = request.data.get('action')
    gmail_ids = [i for i in (request.data.get('gmail_ids') or []) if i]
    label_ids = request.data.get('label_ids') or []
    if not gmail_ids:
        return Response({'detail': 'gmail_ids required'}, status=400)
    if action not in {'archive', 'delete', 'labels', 'move'}:
        return Response({'detail': f'Unknown action {action}'}, status=400)
    if action in {'labels', 'move'} and not label_ids:
        return Response({'detail': 'label_ids required'}, status=400)

    try:
        service = gmail_api.build_gmail_service(account.refresh_token)
    except Exception as exc:  # noqa: BLE001
        return Response({'detail': str(exc)}, status=400)

    ok_ids = []
    errors = []
    for gid in gmail_ids:
        try:
            if action == 'delete':
                gmail_api.trash_message(service, gid)
                EmailSummary.objects.filter(account=account, gmail_id=gid).update(
                    status='deleted'
                )
            elif action == 'archive':
                gmail_api.archive_message(service, gid)
                EmailSummary.objects.filter(account=account, gmail_id=gid).update(
                    status='archived'
                )
            elif action == 'labels':
                gmail_api.modify_labels(service, gid, add=label_ids)
            elif action == 'move':
                gmail_api.modify_labels(
                    service, gid, add=label_ids, remove=['INBOX']
                )
                EmailSummary.objects.filter(account=account, gmail_id=gid).update(
                    status='archived'
                )
            ok_ids.append(gid)
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{gid}: {exc}')
    return Response(
        {'ok': True, 'action': action, 'done': ok_ids, 'errors': errors}
    )


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def schedules_view(request):
    if request.method == 'GET':
        rows = SummarizeSchedule.objects.filter(user=request.user).select_related(
            'account'
        )
        return Response(
            {'schedules': SummarizeScheduleSerializer(rows, many=True).data}
        )

    ser = SummarizeScheduleSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    account = get_active_account(
        request.user, ser.validated_data.pop('account_id', None)
    )
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    obj = SummarizeSchedule.objects.create(
        user=request.user,
        account=account,
        **ser.validated_data,
    )
    return Response(
        {'schedule': SummarizeScheduleSerializer(obj).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def schedule_detail(request, schedule_id):
    obj = get_object_or_404(SummarizeSchedule, id=schedule_id, user=request.user)
    if request.method == 'DELETE':
        obj.delete()
        return Response({'ok': True, 'id': str(schedule_id)})

    ser = SummarizeScheduleSerializer(obj, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    account_id = ser.validated_data.pop('account_id', None)
    if account_id is not None:
        account = get_active_account(request.user, account_id)
        if not account:
            return Response({'detail': 'Unknown Gmail account.'}, status=400)
        obj.account = account
    for key, value in ser.validated_data.items():
        setattr(obj, key, value)
    obj.save()
    return Response({'schedule': SummarizeScheduleSerializer(obj).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def schedule_run_now(request, schedule_id):
    obj = get_object_or_404(SummarizeSchedule, id=schedule_id, user=request.user)
    async_result = run_summarize_schedule.delay(str(obj.id))
    return Response({'ok': True, 'task_id': async_result.id, 'schedule_id': str(obj.id)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def summarize(request):
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    gmail_ids = [i for i in (request.data.get('gmail_ids') or []) if i]
    if not gmail_ids:
        return Response({'detail': 'gmail_ids required'}, status=400)
    force = bool(request.data.get('force'))
    job = LlmJob.objects.create(
        user=request.user,
        account=account,
        kind=LlmJob.KIND_SUMMARIZE,
        gmail_ids=gmail_ids,
    )
    async_result = summarize_emails_task.delay(str(job.id), request.user.id, force)
    job.celery_task_id = async_result.id
    job.save(update_fields=['celery_task_id', 'updated_at'])
    return Response({'ok': True, 'task_id': async_result.id, 'job_id': str(job.id)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_prompt(request):
    account = _account_from_request(request)
    if not account:
        return Response({'detail': 'Connect a Gmail account first.'}, status=400)
    gmail_ids = [i for i in (request.data.get('gmail_ids') or []) if i]
    prompt = (request.data.get('prompt') or '').strip()
    if not gmail_ids:
        return Response({'detail': 'gmail_ids required'}, status=400)
    if not prompt:
        return Response({'detail': 'prompt required'}, status=400)
    job = LlmJob.objects.create(
        user=request.user,
        account=account,
        kind=LlmJob.KIND_PROCESS,
        gmail_ids=gmail_ids,
        prompt=prompt,
    )
    async_result = process_emails_task.delay(str(job.id))
    job.celery_task_id = async_result.id
    job.save(update_fields=['celery_task_id', 'updated_at'])
    return Response({'ok': True, 'task_id': async_result.id, 'job_id': str(job.id)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_progress(request, task_id):
    progress = cache.get(f'task_progress_{task_id}')
    if progress:
        return Response(progress)
    result = AsyncResult(task_id)
    if result.state == 'PENDING':
        return Response(
            {
                'task_id': task_id,
                'status': 'pending',
                'message': 'Queued…',
                'percentage': 0,
            }
        )
    if result.failed():
        return Response(
            {
                'task_id': task_id,
                'status': 'failed',
                'message': str(result.result),
                'percentage': 0,
            },
            status=500,
        )
    if result.successful():
        data = result.result if isinstance(result.result, dict) else {'result': result.result}
        return Response(
            {
                'task_id': task_id,
                'status': 'completed',
                'percentage': 100,
                'message': 'Done',
                **data,
            }
        )
    return Response(
        {
            'task_id': task_id,
            'status': result.state.lower(),
            'message': result.state,
            'percentage': 0,
        }
    )
