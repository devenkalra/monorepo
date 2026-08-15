"""Run show generation with a persisted step log for the SPA."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from django.db import close_old_connections

from .analyze import analysis_is_fresh, ensure_item_analysis, source_key
from .compiler import compile_show
from .models import GalleryShow, ShowBuildJob
from .planner import build_plan, llm_available
from .utils import unique_show_slug

logger = logging.getLogger(__name__)

_STATUS_STEPS = {
    ShowBuildJob.STATUS_ANALYZING,
    ShowBuildJob.STATUS_PLANNING,
    ShowBuildJob.STATUS_COMPILING,
    ShowBuildJob.STATUS_READY,
    ShowBuildJob.STATUS_FAILED,
}


def start_generate_job(job_id):
    thread = threading.Thread(
        target=_thread_run,
        args=(str(job_id),),
        name=f'gallery-generate-{job_id}',
        daemon=True,
    )
    thread.start()


def _thread_run(job_id: str):
    close_old_connections()
    try:
        run_generate_job(job_id)
    finally:
        close_old_connections()


def append_log(job, step, message, level='info', data=None, status=None):
    entry = {
        't': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'step': step,
        'level': level,
        'message': message,
    }
    if data:
        entry['data'] = _json_safe(data)
    log = list(job.log or [])
    log.append(entry)
    job.log = log
    fields = ['log', 'updated_at']
    next_status = status or (step if step in _STATUS_STEPS else None)
    if next_status:
        job.status = next_status
        fields.append('status')
    job.save(update_fields=fields)
    return entry


def run_generate_job(job_id: str):
    job = ShowBuildJob.objects.select_related('gallery').get(id=job_id)
    gallery = job.gallery
    items_by_id = {str(it.id): it for it in gallery.items.all()}
    ordered = [str(i) for i in (job.item_ids or []) if str(i) in items_by_id]
    skipped = [str(i) for i in (job.item_ids or []) if str(i) not in items_by_id]

    def log(step, message, level='info', data=None, status=None):
        append_log(job, step, message, level=level, data=data, status=status)

    try:
        log(
            'queued',
            f'Started generate for {len(ordered)} image(s).',
            data={
                'title': job.title,
                'style': job.style,
                'target_seconds': job.target_seconds,
                'prompt': (job.prompt or '')[:200],
                'localai': llm_available(),
            },
        )
        if skipped:
            log('queued', f'{len(skipped)} selected id(s) are not images in this gallery.', level='warn')

        selected = [items_by_id[k] for k in ordered]
        log('analyzing', f'Analyzing {len(selected)} image(s).', status=ShowBuildJob.STATUS_ANALYZING)
        for item in selected:
            url = source_key(item)
            cached = analysis_is_fresh(getattr(item, 'analysis', None) or {}, url)
            analysis = ensure_item_analysis(item)
            faces = analysis.get('faces') if isinstance(analysis, dict) else []
            nfaces = len(faces) if isinstance(faces, list) else 0
            subject = (analysis or {}).get('subject') or {}
            log(
                'analyzing',
                (
                    f'{item.filename or item.id}: '
                    f'{"cache" if cached else "scan"} '
                    f'faces={nfaces} subject={subject.get("x", 0.5)},{subject.get("y", 0.5)} '
                    f'blur={analysis.get("blur")} {analysis.get("orientation") or ""}'
                ).strip(),
                data={
                    'item_id': str(item.id),
                    'filename': item.filename,
                    'cache': cached,
                    'faces': nfaces,
                    'subject': subject,
                    'blur': analysis.get('blur'),
                    'detector': analysis.get('detector'),
                    'width': analysis.get('width'),
                    'height': analysis.get('height'),
                },
            )

        log('planning', 'Building shot list.', status=ShowBuildJob.STATUS_PLANNING)
        plan = build_plan(
            ordered,
            items_by_id=items_by_id,
            prompt=job.prompt or '',
            title=job.title,
            style=job.style,
            target_seconds=job.target_seconds,
            on_log=log,
        )
        job.plan = {
            'planner': plan.get('planner'),
            'title': plan.get('title'),
            'style': plan.get('style'),
            'shots': plan.get('shots'),
        }
        job.save(update_fields=['plan', 'updated_at'])

        title = (job.title or 'Show').strip() or 'Show'
        if plan.get('title') and title.lower() in {'', 'show'}:
            title = str(plan['title']).strip()[:80] or title

        blurry = plan.get('skipped_blurry') or []
        log('compiling', 'Compiling show JSON.', status=ShowBuildJob.STATUS_COMPILING)
        try:
            config, warnings = compile_show(
                plan,
                {k: items_by_id[k] for k in ordered},
                style=job.style,
                target_seconds=job.target_seconds,
            )
        except ValueError as exc:
            detail = str(exc)
            if blurry and not plan.get('shots'):
                detail = 'All selected images look too blurry to include.'
            raise ValueError(detail) from exc

        for slide in config.get('slides') or []:
            views = slide.get('views') or []
            focus = views[0] if views else {}
            log(
                'compiling',
                (
                    f'clip {slide.get("item_id")} t={slide.get("start")}s '
                    f'dur={slide.get("duration")}s focus={focus.get("x")},{focus.get("y")} '
                    f'zoom→{views[-1].get("zoom") if views else "?"}'
                ),
                data={
                    'item_id': slide.get('item_id'),
                    'start': slide.get('start'),
                    'duration': slide.get('duration'),
                    'x': focus.get('x'),
                    'y': focus.get('y'),
                },
            )

        notes = list(warnings)
        if skipped:
            notes.append(f'Skipped {len(skipped)} non-image or unknown item(s).')
        if blurry:
            notes.append(f'Skipped {len(blurry)} blurry image(s).')
        used = {str(s.get('item_id')) for s in (plan.get('shots') or [])}
        no_face = sum(
            1
            for key in used
            if not (getattr(items_by_id.get(key), 'analysis', None) or {}).get('faces')
        )
        if no_face:
            notes.append(f'No face found on {no_face} image(s); Ken Burns aims at center.')
        if plan.get('planner') == 'llm':
            notes.append('Shot list from LocalAI.')
        elif plan.get('planner_error'):
            notes.append(f'LocalAI plan unused ({plan["planner_error"]}); used your order.')
        for extra in plan.get('planner_warnings') or []:
            notes.append(extra)

        slug = unique_show_slug(gallery, title)
        show = GalleryShow.objects.create(
            gallery=gallery,
            title=title,
            slug=slug,
            config=config,
        )
        job.show = show
        job.title = title
        job.warnings = notes
        job.status = ShowBuildJob.STATUS_READY
        job.error = ''
        job.save(update_fields=['show', 'title', 'warnings', 'status', 'error', 'updated_at'])
        log(
            'ready',
            f'Show ready: {title} ({len(config.get("slides") or [])} clips).',
            status=ShowBuildJob.STATUS_READY,
            data={'show_id': str(show.id), 'slug': slug, 'warnings': notes},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('Show generate job %s failed', job_id)
        job.error = str(exc)
        job.status = ShowBuildJob.STATUS_FAILED
        job.save(update_fields=['error', 'status', 'updated_at'])
        append_log(job, 'failed', str(exc), level='error', status=ShowBuildJob.STATUS_FAILED)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
