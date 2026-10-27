"""Executes SyncRuns with the engine, storing progress, review items and the change journal."""
import gzip
import hashlib
import json
import logging
import math
import re
import sys
import time
import traceback
import uuid
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Exists
from django.utils import timezone

from .engine import ClickUp, WriteGuard, open_list, run_sync
from .engine import transfer
from .engine.errors import ConfigError, RunCancelled, SafetyStop
from .models import ChangeLog, ContactsState, EntityEdit, ImportedTask, ReviewItem, SourceFile, SyncRun

logger = logging.getLogger(__name__)

SYNC_TOKEN_KEY = 'google_sync_token'
IGNORE_KEY = 'ignore_labels'
CHECK_KEY = 'last_check'
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
STALE_AFTER = timedelta(minutes=10)
FLUSH_EVERY_S = 2.0
LIVE_SOURCES = ('google', 'linkedin', 'whatsapp', 'import', 'merge')
LIST_ID_RE = re.compile(r'^\d{6,20}$')


class ApplyRefused(Exception):
    pass


def data_dir():
    d = Path(getattr(settings, 'CONTACTS_DATA_DIR', Path(settings.BASE_DIR) / 'contacts_data'))
    d.mkdir(parents=True, exist_ok=True)
    return d


def writes_enabled():
    return bool(getattr(settings, 'CONTACTS_CLICKUP_WRITES_ENABLED', False))


def clickup_config():
    return (getattr(settings, 'CONTACTS_CLICKUP_TOKEN', '') or getattr(settings, 'CLICKUP_API_TOKEN', ''),
            getattr(settings, 'CONTACTS_CLICKUP_LIST_ID', ''))


def orgs_list_id():
    return getattr(settings, 'CONTACTS_CLICKUP_ORGS_LIST_ID', '')


def plan_budget(planned_ops):
    return math.ceil(planned_ops * 1.2) + 10


# ---- uploads ----------------------------------------------------------------------------
def save_upload(kind, uploaded):
    from .engine.sources import linkedin, whatsapp

    if kind not in SourceFile.Kind.values:
        raise ConfigError(f'Unknown file kind {kind!r}')
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ConfigError('File is larger than 50 MB.')
    data = uploaded.read()
    sniff = {
        SourceFile.Kind.LINKEDIN_CONNECTIONS: linkedin.sniff_connections,
        SourceFile.Kind.LINKEDIN_MESSAGES: linkedin.sniff_messages,
        SourceFile.Kind.WHATSAPP: whatsapp.sniff_export,
        SourceFile.Kind.CONTACTS_EXPORT: lambda d: transfer.check_export(load_export(d)),
    }[kind]
    rows = sniff(data)
    return _store_file(kind, uploaded.name, data, rows, 'uploads')


def _store_file(kind, name, data, rows, folder):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(name).name)[-120:] or 'upload'
    rel = Path(folder) / f'{uuid.uuid4().hex}_{safe}'
    target = data_dir() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return SourceFile.objects.create(kind=kind, original_name=name[:255], path=str(rel.as_posix()),
                                     size=len(data), rows=rows, sha256=hashlib.sha256(data).hexdigest())


def load_export(data):
    """Parse an export file (plain or gzipped JSON)."""
    try:
        if data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)
        return json.loads(data.decode('utf-8'))
    except (OSError, ValueError) as e:
        raise ConfigError(f"This isn't a contacts export file ({e}).")


def _file_paths(run):
    by_kind = {f.kind: data_dir() / f.path for f in run.files.all()}
    for p in by_kind.values():
        if not p.exists():
            raise ConfigError(f'Uploaded file is missing on disk: {p.name}')
    return {
        'connections': by_kind.get(SourceFile.Kind.LINKEDIN_CONNECTIONS),
        'messages': by_kind.get(SourceFile.Kind.LINKEDIN_MESSAGES),
        'export': by_kind.get(SourceFile.Kind.WHATSAPP),
    }


# ---- progress + journal -----------------------------------------------------------------
class DbReporter:
    def __init__(self, run, echo=False):
        self.run, self.echo = run, echo
        self.actions, self.stats = [], Counter()
        self.phase, self.done, self.total = '', 0, 0
        self.guard = None
        self._last_flush = self._last_cancel = 0.0

    def action(self, entry):
        self.actions.append(entry)
        self.stats[entry['action']] += 1
        if self.echo and entry['action'] != 'UNCHANGED':
            dry = '' if self.run.is_live else '[dry] '
            _safe_print(f"{dry}{entry['action']:<10} {entry['name']}  {entry['detail']}")
        self._maybe_flush()

    def progress(self, phase, done=0, total=0):
        self.phase, self.done, self.total = phase, done, total
        self._maybe_flush()

    def check_cancel(self):
        now = time.monotonic()
        if now - self._last_cancel < FLUSH_EVERY_S:
            return
        self._last_cancel = now
        if SyncRun.objects.filter(pk=self.run.pk, cancel_requested=True).exists():
            raise RunCancelled('Cancelled.')

    def _maybe_flush(self):
        if time.monotonic() - self._last_flush >= FLUSH_EVERY_S:
            self.flush()

    def flush(self, **extra):
        self._last_flush = time.monotonic()
        SyncRun.objects.filter(pk=self.run.pk).update(
            actions=self.actions, stats=dict(self.stats), phase=self.phase[:80],
            progress_done=self.done, progress_total=self.total,
            ops=self.guard.ops if self.guard else 0, heartbeat_at=timezone.now(), **extra)


class DbJournal:
    def __init__(self, run):
        self.run = run

    def record(self, *, op, task_id, task_name, field, before, after):
        return ChangeLog.objects.create(run=self.run, op=op, task_id=task_id, task_name=task_name[:500],
                                        field=field, before=_jsonable(before), after=_jsonable(after)).pk

    def finish(self, pk, error=None):
        ChangeLog.objects.filter(pk=pk).update(ok=error is None, error=(error or '')[:2000])


def _safe_print(text):
    enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    print(text.encode(enc, errors='replace').decode(enc, errors='replace'))


def _jsonable(v):
    return json.loads(json.dumps(v, default=str))


def _write_snapshot(run, ix):
    rel = Path('snapshots') / f'run-{run.pk}-{timezone.now():%Y%m%d-%H%M%S}.json.gz'
    path = data_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with gzip.open(path, 'wt', encoding='utf-8') as fh:
            json.dump({'run': run.pk, 'list_id': clickup_config()[1], 'taken_at': timezone.now().isoformat(),
                       'contacts': ix.snapshot()}, fh, default=str)
    except OSError as e:
        raise SafetyStop(f'Could not save the pre-run snapshot ({e}); nothing was written.')
    run.snapshot_path = rel.as_posix()
    SyncRun.objects.filter(pk=run.pk).update(snapshot_path=run.snapshot_path)


def _decisions(source):
    return {r.key: {'decision': r.decision, 'task_id': r.chosen_task_id or r.suggested_task_id}
            for r in ReviewItem.objects.filter(source=source).exclude(decision=ReviewItem.Decision.PENDING)}


def _save_review_rows(run, rows):
    for row in rows:
        ReviewItem.objects.update_or_create(
            source=run.source, key=row['key'],
            defaults={'name': row['name'][:500], 'company': row['company'][:500], 'title': row['title'][:500],
                      'suggested_task_id': row['suggested_task_id'],
                      'suggested_task_name': row['suggested_task_name'][:500], 'note': row.get('note', ''),
                      'decision': ReviewItem.Decision.PENDING, 'chosen_task_id': '', 'decided_by': '',
                      'decided_at': None, 'last_seen_run': run})


# ---- executing --------------------------------------------------------------------------
def execute_run(run, echo=False, token_file=None):
    reporter = DbReporter(run, echo=echo)
    live = run.is_live
    guard = WriteGuard(dry=not live, writes_enabled=writes_enabled(), max_ops=run.max_ops if live else None,
                       journal=DbJournal(run) if live else None)
    reporter.guard = guard
    ctx, status, error = None, SyncRun.Status.DONE, ''
    try:
        if live:
            if not writes_enabled():
                raise SafetyStop('Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).')
            if not run.max_ops:
                raise SafetyStop('Live run has no write budget.')
        token = clickup_config()[0]
        if run.source == SyncRun.Source.EXPORT:
            ctx = _run_export(run, token, guard, reporter)
        elif run.source == SyncRun.Source.IMPORT:
            ctx = _run_import(run, token, guard, reporter)
        else:
            ctx = _run_sync(run, guard, reporter, token_file)
    except RunCancelled:
        status, error = SyncRun.Status.CANCELLED, 'Cancelled.'
    except SafetyStop as e:
        status, error = SyncRun.Status.STOPPED, str(e)
    except ConfigError as e:
        status, error = SyncRun.Status.FAILED, str(e)
    except Exception as e:  # noqa: BLE001 - report anything else on the run
        logger.exception('Contacts run %s failed', run.pk)
        status, error = SyncRun.Status.FAILED, f'{e}\n\n{traceback.format_exc(limit=6)}'
    finally:
        extra = {'status': status, 'error': error, 'finished_at': timezone.now()}
        if ctx is not None:
            extra.update(warnings=ctx.warnings, unknown_groups=dict(ctx.unknown_groups),
                         unknown_sources=sorted(ctx.unknown_sources))
        reporter.flush(**extra)
    run.refresh_from_db()
    return run


def _run_sync(run, guard, reporter, token_file):
    token, list_id = clickup_config()
    cu, missing = open_list(token, list_id, guard)
    if missing:
        raise ConfigError(f"Missing required ClickUp fields: {', '.join(missing)}. Run the list check.")
    opts = dict(run.options)
    service = None
    if run.source == 'google':
        from .google_auth import people_service
        service = people_service(token_file=token_file, write=bool(opts.get('writeback')))
    ctx, result = run_sync(
        source=run.source, cu=cu, reporter=reporter, options=opts, decisions=_decisions(run.source),
        files=_file_paths(run) if run.source in ('linkedin', 'whatsapp') else None,
        google_service=service, sync_token=ContactsState.get(SYNC_TOKEN_KEY),
        on_index=(lambda ix: _write_snapshot(run, ix)) if run.is_live else None)
    _save_review_rows(run, ctx.review_rows)
    if run.is_live and run.source == 'google' and result.get('next_sync_token'):
        ContactsState.put(SYNC_TOKEN_KEY, result['next_sync_token'])
    return ctx


def _run_export(run, token, guard, reporter):
    lists = {'people': run.options.get('people_list_id') or clickup_config()[1],
             'orgs': run.options.get('orgs_list_id') or orgs_list_id()}
    lists = {k: v for k, v in lists.items() if v}
    if not token or 'people' not in lists:
        raise ConfigError('Set CONTACTS_CLICKUP_LIST_ID and a ClickUp token (CLICKUP_API_TOKEN).')
    data, log = transfer.export_lists({k: ClickUp(token, v, guard) for k, v in lists.items()}, reporter=reporter)
    if 'orgs' not in lists:
        log.warn('No Orgs list is configured (CONTACTS_CLICKUP_ORGS_LIST_ID), so only People was exported.')
    body = json.dumps(data, ensure_ascii=False, indent=1, default=str).encode('utf-8')
    name = f'contacts-export-{timezone.localtime():%Y%m%d-%H%M%S}.json'
    rows = sum(len(lst['tasks']) for lst in data['lists'].values())
    run.output = _store_file(SourceFile.Kind.CONTACTS_EXPORT, name, body, rows, 'exports')
    SyncRun.objects.filter(pk=run.pk).update(output=run.output)
    return log


def check_import_targets(options, export_file):
    """Validate (and trim) an import's target list IDs against the export file. Raises ConfigError."""
    data = load_export((data_dir() / export_file.path).read_bytes())
    live = {clickup_config()[1], orgs_list_id()} - {''}
    chosen = []
    for key, label in transfer.LISTS.items():
        list_id = options.get(f'{key}_list_id', '')
        if key not in data.get('lists', {}):
            options.pop(f'{key}_list_id', None)
            continue
        if not LIST_ID_RE.match(list_id or ''):
            raise ConfigError(f'Enter the ClickUp list ID to import {label} into (digits only).')
        if list_id in live:
            raise ConfigError(f'{list_id} is one of the lists Contact Sync uses. Import into a new, empty list.')
        chosen.append(list_id)
    if len(set(chosen)) < len(chosen):
        raise ConfigError('People and Orgs need different target lists.')


def import_key(export_file, targets):
    return f"{export_file.sha256}:{targets.get('people', '')}:{targets.get('orgs', '')}"


def _run_import(run, token, guard, reporter):
    export_file = run.files.filter(kind=SourceFile.Kind.CONTACTS_EXPORT).first()
    if not export_file:
        raise ConfigError('Choose an export file to import.')
    path = data_dir() / export_file.path
    if not path.exists():
        raise ConfigError(f'The export file is missing on disk: {export_file.original_name}')
    data = load_export(path.read_bytes())
    targets = {k: str(run.options.get(f'{k}_list_id') or '') for k in transfer.LISTS}
    targets = {k: v for k, v in targets.items() if v}
    key = import_key(export_file, targets)
    done = dict(ImportedTask.objects.filter(import_key=key).values_list('source_id', 'target_id'))

    def remember(list_key, old, new):
        ImportedTask.objects.create(import_key=key, list_key=list_key, source_id=old, target_id=new, run=run)

    log, _ = transfer.import_lists(data, {k: ClickUp(token, v, guard) for k, v in targets.items()},
                                   reporter=reporter, id_map=done, on_mapped=remember if run.is_live else None)
    return log


# ---- queueing ---------------------------------------------------------------------------
def active_run():
    return SyncRun.objects.filter(status__in=[SyncRun.Status.QUEUED, SyncRun.Status.RUNNING]).first()


def claim(run_id=None, foreground=False):
    """Mark a queued run as running, but only if no other run is running (atomic in one UPDATE)."""
    running = SyncRun.objects.filter(status=SyncRun.Status.RUNNING)
    queued = SyncRun.objects.filter(status=SyncRun.Status.QUEUED, foreground=foreground).order_by('id')
    if run_id:
        queued = queued.filter(pk=run_id)
    for run in queued[:5]:
        now = timezone.now()
        n = (SyncRun.objects.filter(pk=run.pk, status=SyncRun.Status.QUEUED)
             .filter(~Exists(running))
             .update(status=SyncRun.Status.RUNNING, started_at=now, heartbeat_at=now))
        if n:
            return SyncRun.objects.get(pk=run.pk)
    return None


def recover_stale():
    cutoff = timezone.now() - STALE_AFTER
    SyncRun.objects.filter(status=SyncRun.Status.RUNNING, heartbeat_at__lt=cutoff).update(
        status=SyncRun.Status.INTERRUPTED, finished_at=timezone.now(),
        error='The server stopped while this run was in progress. Check its change log, then run a new preview.')


def apply_refusal(plan):
    """Why this dry run can't be applied right now, or None if it can."""
    if plan.mode != SyncRun.Mode.DRY or plan.status != SyncRun.Status.DONE:
        return 'Only a finished dry run can be applied.'
    if plan.source == SyncRun.Source.EXPORT:
        return 'Exports only read ClickUp; download the file instead.'
    if plan.source not in LIVE_SOURCES:
        return 'This kind of run can only be applied from the command line.'
    if not writes_enabled():
        return ('Live ClickUp writes are disabled on this server '
                '(set CONTACTS_CLICKUP_WRITES_ENABLED=1 to allow them).')
    max_age = timedelta(hours=float(getattr(settings, 'CONTACTS_PLAN_MAX_AGE_HOURS', 24)))
    if plan.finished_at is None or timezone.now() - plan.finished_at > max_age:
        return 'This preview is too old; run a new one.'
    if plan.applied_by.exists():
        return 'This preview was already applied; run a new one.'
    if SyncRun.objects.filter(mode=SyncRun.Mode.LIVE, finished_at__gt=plan.started_at).exists():
        return 'ClickUp changed since this preview (another live run finished); run a new one.'
    if EntityEdit.objects.filter(at__gt=plan.started_at).exists():
        return 'Contacts were edited in People & Orgs since this preview; run a new one so it includes the edits.'
    if ReviewItem.objects.filter(source=plan.source, decided_at__gt=plan.started_at).exists():
        return 'Review decisions changed since this preview; run a new one so it includes them.'
    if plan.ops == 0:
        return 'Nothing to apply: the preview found no changes.'
    if active_run():
        return 'Another run is queued or running.'
    return None


def create_live_from_plan(plan, user=''):
    """A live run that applies a finished dry run, with a write budget derived from it."""
    reason = apply_refusal(plan)
    if reason:
        raise ApplyRefused(reason)
    live = SyncRun.objects.create(source=plan.source, mode=SyncRun.Mode.LIVE, options=plan.options, plan=plan,
                                  max_ops=plan_budget(plan.ops), created_by=user)
    live.files.set(plan.files.all())
    return live
