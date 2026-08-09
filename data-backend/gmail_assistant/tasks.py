"""Celery tasks for summarize / process."""

from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache

from . import gmail_api, llm
from .models import GmailAccount, LlmJob
from .services import get_or_create_prefs, upsert_summary

logger = logging.getLogger(__name__)
User = get_user_model()


def update_task_progress(task_id, current, total, message, status='processing', extra=None):
    progress_data = {
        'task_id': task_id,
        'status': status,
        'current': current,
        'total': total,
        'percentage': int((current / total * 100)) if total > 0 else 0,
        'message': message,
    }
    if extra:
        progress_data.update(extra)
    cache.set(f'task_progress_{task_id}', progress_data, timeout=3600)
    return progress_data


@shared_task(bind=True)
def summarize_emails_task(self, job_id: str, user_id: int, force: bool = False):
    task_id = self.request.id
    job = LlmJob.objects.select_related('account', 'user').get(id=job_id)
    job.celery_task_id = task_id
    job.status = LlmJob.STATUS_PROCESSING
    job.save(update_fields=['celery_task_id', 'status', 'updated_at'])

    prefs = get_or_create_prefs(job.user)
    ids = list(job.gmail_ids or [])
    total = max(1, len(ids))
    update_task_progress(task_id, 0, total, 'Starting summarize…')
    done = []
    skipped = []
    errors = []

    try:
        service = gmail_api.build_gmail_service(job.account.refresh_token)
    except Exception as exc:  # noqa: BLE001
        job.status = LlmJob.STATUS_FAILED
        job.errors = [str(exc)]
        job.save(update_fields=['status', 'errors', 'updated_at'])
        update_task_progress(task_id, 0, total, str(exc), status='failed')
        return {'ok': False, 'error': str(exc)}

    for i, gid in enumerate(ids, start=1):
        update_task_progress(
            task_id, i - 1, total, f'Summarizing {i}/{len(ids)}…', extra={'gmail_id': gid}
        )
        try:
            from .models import EmailSummary

            existing = EmailSummary.objects.filter(
                account=job.account, gmail_id=gid
            ).first()
            if (
                existing
                and not force
                and not prefs.zero_knowledge
                and (existing.brief_summary or '').strip()
            ):
                skipped.append(gid)
                continue
            if (
                existing
                and not force
                and prefs.zero_knowledge
                and existing.category
            ):
                # Session chip is client-side; still skip re-LLM if we have category.
                skipped.append(gid)
                continue

            message = gmail_api.fetch_message(service, gid)
            block = llm.format_email_block(message, i)
            summary = llm.summarize_email_text(block)
            upsert_summary(
                user=job.user,
                account=job.account,
                message=message,
                summary=summary,
                zero_knowledge=prefs.zero_knowledge,
            )
            done.append(gid)
        except Exception as exc:  # noqa: BLE001
            logger.exception('summarize failed for %s', gid)
            errors.append(f'{gid}: {exc}')

    job.status = LlmJob.STATUS_COMPLETED if not errors else LlmJob.STATUS_FAILED
    job.errors = errors
    job.progress = {'done': done, 'skipped': skipped}
    job.save(update_fields=['status', 'errors', 'progress', 'updated_at'])
    result = {
        'ok': True,
        'done': done,
        'skipped': skipped,
        'errors': errors,
        'zero_knowledge': prefs.zero_knowledge,
    }
    update_task_progress(
        task_id,
        total,
        total,
        f'Done · {len(done)} summarized, {len(skipped)} skipped',
        status='completed',
        extra=result,
    )
    return result


@shared_task(bind=True)
def process_emails_task(self, job_id: str):
    task_id = self.request.id
    job = LlmJob.objects.select_related('account', 'user').get(id=job_id)
    job.celery_task_id = task_id
    job.status = LlmJob.STATUS_PROCESSING
    job.save(update_fields=['celery_task_id', 'status', 'updated_at'])

    prefs = get_or_create_prefs(job.user)
    ids = list(job.gmail_ids or [])
    update_task_progress(task_id, 0, max(1, len(ids)), 'Fetching emails…')

    try:
        service = gmail_api.build_gmail_service(job.account.refresh_token)
        messages = []
        for i, gid in enumerate(ids, start=1):
            update_task_progress(
                task_id, i, len(ids), f'Fetching {i}/{len(ids)}…'
            )
            messages.append(gmail_api.fetch_message(service, gid))

        def on_progress(ev):
            update_task_progress(
                task_id,
                ev.get('batch') or 0,
                max(1, len(ids)),
                ev.get('message') or 'Processing…',
                extra=ev,
            )

        result_text = llm.run_process_prompt(
            user_prompt=job.prompt,
            messages=messages,
            context_size=prefs.llm_context_size,
            on_progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('process failed')
        job.status = LlmJob.STATUS_FAILED
        job.errors = [str(exc)]
        job.save(update_fields=['status', 'errors', 'updated_at'])
        update_task_progress(task_id, 0, 1, str(exc), status='failed')
        return {'ok': False, 'error': str(exc)}

    # ZK: discard result from server storage; still return via cache for client poll.
    if prefs.zero_knowledge:
        job.result = ''
    else:
        job.result = result_text
    job.status = LlmJob.STATUS_COMPLETED
    job.save(update_fields=['result', 'status', 'updated_at'])
    payload = {
        'ok': True,
        'result': result_text,
        'zero_knowledge': prefs.zero_knowledge,
        'email_count': len(messages),
    }
    update_task_progress(
        task_id,
        len(ids),
        max(1, len(ids)),
        'Done',
        status='completed',
        extra=payload,
    )
    return payload
