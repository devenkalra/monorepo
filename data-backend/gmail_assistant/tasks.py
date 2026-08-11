"""Celery tasks for summarize / process / enrich-links / scheduled summarize."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from . import gmail_api, link_enrichment, llm
from .models import LlmJob, SummarizeSchedule
from .nl_query import nl_to_gmail_query
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
    logger.info(
        'summarize job=%s emails=%s force=%s localai_url=%s',
        job_id,
        len(ids),
        force,
        bool(llm._localai_url()),
    )
    update_task_progress(task_id, 0, total, 'Starting summarize…')
    done = []
    skipped = []
    errors = []
    # Full summary payloads for the client (esp. ZK: not persisted, shown this session).
    summaries_out: dict = {}

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
            # Non-ZK: skip when we already have stored summary text.
            # ZK: never skip — text is not in DB; client needs a fresh payload.
            if (
                existing
                and not force
                and not prefs.zero_knowledge
                and (existing.brief_summary or '').strip()
            ):
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
            summaries_out[gid] = {
                'brief_summary': summary.get('brief_summary') or '',
                'key_points': summary.get('key_points') or [],
                'details': summary.get('details') or '',
                'category': summary.get('category') or '',
                'category_confidence': float(
                    summary.get('category_confidence') or 0
                ),
                'has_summary': True,
            }
            done.append(gid)
        except Exception as exc:  # noqa: BLE001
            logger.exception('summarize failed for %s', gid)
            errors.append(f'{gid}: {exc}')

    job.status = LlmJob.STATUS_COMPLETED if not errors else LlmJob.STATUS_FAILED
    job.errors = errors
    # Do not persist summary text on the job in ZK mode.
    job.progress = {
        'done': done,
        'skipped': skipped,
        **({'summaries': summaries_out} if not prefs.zero_knowledge else {}),
    }
    job.save(update_fields=['status', 'errors', 'progress', 'updated_at'])
    result = {
        'ok': True,
        'done': done,
        'skipped': skipped,
        'errors': errors,
        'zero_knowledge': prefs.zero_knowledge,
        'summaries': summaries_out,
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


@shared_task(bind=True)
def enrich_links_task(self, job_id: str):
    """Fetch linked content per email, then store structured summaries (like Summarize)."""
    task_id = self.request.id
    job = LlmJob.objects.select_related('account', 'user').get(id=job_id)
    job.celery_task_id = task_id
    job.status = LlmJob.STATUS_PROCESSING
    job.save(update_fields=['celery_task_id', 'status', 'updated_at'])

    prefs = get_or_create_prefs(job.user)
    ids = list(job.gmail_ids or [])
    total = max(1, len(ids))
    update_task_progress(task_id, 0, total, 'Starting enrich links…')

    done: list[str] = []
    errors: list[str] = []
    summaries_out: dict = {}
    link_stats = {'urls': 0, 'ok': 0, 'failed': 0, 'by_kind': {}}

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
            task_id,
            i - 1,
            total,
            f'Enriching {i}/{len(ids)}…',
            extra={'gmail_id': gid},
        )
        try:
            message = gmail_api.fetch_message(service, gid)

            def on_enrich_progress(message_text: str, _i=i):
                update_task_progress(
                    task_id, _i - 1, total, f'Email {_i}/{len(ids)} · {message_text}'
                )

            enriched = link_enrichment.enrich_message(
                message, on_progress=on_enrich_progress
            )
            for enr in enriched.get('enrichments') or []:
                link_stats['urls'] += 1
                kind = enr.get('kind') or 'web'
                link_stats['by_kind'][kind] = link_stats['by_kind'].get(kind, 0) + 1
                if enr.get('ok'):
                    link_stats['ok'] += 1
                else:
                    link_stats['failed'] += 1

            update_task_progress(
                task_id, i - 1, total, f'Summarizing {i}/{len(ids)} with links…'
            )
            block = f'===== Email {i} =====\n{enriched["block"]}'
            summary = llm.summarize_email_text(block, with_linked_content=True)
            # Always attach verbatim transcripts so the UI summary has full text
            # (the LLM is instructed not to paste them into details itself).
            details = link_enrichment.append_full_transcripts_to_details(
                summary.get('details') or '',
                enriched.get('enrichments') or [],
            )
            summary['details'] = details
            upsert_summary(
                user=job.user,
                account=job.account,
                message=message,
                summary=summary,
                zero_knowledge=prefs.zero_knowledge,
            )
            summaries_out[gid] = {
                'brief_summary': summary.get('brief_summary') or '',
                'key_points': summary.get('key_points') or [],
                'details': details,
                'category': summary.get('category') or '',
                'category_confidence': float(
                    summary.get('category_confidence') or 0
                ),
                'has_summary': True,
                'enriched_links': True,
            }
            done.append(gid)
        except Exception as exc:  # noqa: BLE001
            logger.exception('enrich_links failed for %s', gid)
            errors.append(f'{gid}: {exc}')

    job.status = LlmJob.STATUS_COMPLETED if not errors else LlmJob.STATUS_FAILED
    job.errors = errors
    job.result = ''
    job.progress = {
        'done': done,
        'link_stats': link_stats,
        **({'summaries': summaries_out} if not prefs.zero_knowledge else {}),
    }
    job.save(update_fields=['status', 'errors', 'result', 'progress', 'updated_at'])
    payload = {
        'ok': True,
        'done': done,
        'errors': errors,
        'zero_knowledge': prefs.zero_knowledge,
        'email_count': len(done),
        'link_stats': link_stats,
        'summaries': summaries_out,
    }
    update_task_progress(
        task_id,
        total,
        total,
        f'Done · {len(done)} enriched, {link_stats["ok"]} links fetched',
        status='completed',
        extra=payload,
    )
    return payload


def _schedule_is_due(schedule: SummarizeSchedule, now) -> bool:
    if not schedule.enabled:
        return False
    if not schedule.last_run_at:
        return True
    return schedule.last_run_at <= now - timedelta(hours=schedule.interval_hours)


@shared_task
def run_due_summarize_schedules():
    """Beat tick: enqueue any enabled schedules whose interval has elapsed."""
    now = timezone.now()
    due_ids = []
    for sched in SummarizeSchedule.objects.filter(enabled=True).select_related(
        'account'
    ):
        if _schedule_is_due(sched, now):
            due_ids.append(str(sched.id))
            run_summarize_schedule.delay(str(sched.id))
    logger.info('summarize schedule tick: due=%s', len(due_ids))
    return {'due': due_ids}


@shared_task(bind=True)
def run_summarize_schedule(self, schedule_id: str):
    """Resolve schedule filter → message ids → summarize_emails_task."""
    try:
        schedule = SummarizeSchedule.objects.select_related('account', 'user').get(
            id=schedule_id
        )
    except SummarizeSchedule.DoesNotExist:
        logger.warning('summarize schedule missing: %s', schedule_id)
        return {'ok': False, 'error': 'not_found'}

    if not schedule.enabled:
        return {'ok': False, 'error': 'disabled'}
    if not schedule.has_filter():
        schedule.last_status = 'failed'
        schedule.last_error = 'Schedule has no search filter'
        schedule.last_run_at = timezone.now()
        schedule.save(
            update_fields=['last_status', 'last_error', 'last_run_at', 'updated_at']
        )
        return {'ok': False, 'error': 'no_filter'}

    try:
        parsed = nl_to_gmail_query(
            schedule.prompt or '',
            start_date=schedule.start_date or None,
            end_date=schedule.end_date or None,
            days=schedule.days,
            keyword=schedule.keyword or None,
        )
        service = gmail_api.build_gmail_service(schedule.account.refresh_token)
        ids = gmail_api.list_message_ids(
            service,
            query=parsed['query'],
            max_results=max(1, min(int(schedule.max_results or 100), 200)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('summarize schedule search failed: %s', schedule_id)
        schedule.last_status = 'failed'
        schedule.last_error = str(exc)[:500]
        schedule.last_run_at = timezone.now()
        schedule.save(
            update_fields=['last_status', 'last_error', 'last_run_at', 'updated_at']
        )
        return {'ok': False, 'error': str(exc)}

    if not ids:
        schedule.last_status = 'completed'
        schedule.last_error = ''
        schedule.last_run_at = timezone.now()
        schedule.save(
            update_fields=['last_status', 'last_error', 'last_run_at', 'updated_at']
        )
        logger.info('summarize schedule %s: no matching emails', schedule_id)
        return {'ok': True, 'count': 0}

    job = LlmJob.objects.create(
        user=schedule.user,
        account=schedule.account,
        kind=LlmJob.KIND_SUMMARIZE,
        gmail_ids=ids,
        prompt=schedule.prompt or '',
    )
    async_result = summarize_emails_task.delay(
        str(job.id), schedule.user_id, schedule.force
    )
    job.celery_task_id = async_result.id
    job.save(update_fields=['celery_task_id', 'updated_at'])

    schedule.last_status = 'queued'
    schedule.last_error = ''
    schedule.last_run_at = timezone.now()
    schedule.last_job = job
    schedule.save(
        update_fields=[
            'last_status',
            'last_error',
            'last_run_at',
            'last_job',
            'updated_at',
        ]
    )
    logger.info(
        'summarize schedule %s queued job=%s emails=%s',
        schedule_id,
        job.id,
        len(ids),
    )
    return {
        'ok': True,
        'job_id': str(job.id),
        'task_id': async_result.id,
        'count': len(ids),
        'query': parsed['query'],
    }
