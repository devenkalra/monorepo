"""In-process background job loop (SQLite-friendly, single-user)."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def start_worker_thread():
    global _started
    with _lock:
        if _started:
            return
        import sys
        if any(cmd in sys.argv for cmd in ('migrate', 'makemigrations', 'test', 'shell', 'collectstatic')):
            return
        t = threading.Thread(target=_loop, name='email-processor-worker', daemon=True)
        t.start()
        _started = True
        logger.info('Email processor worker thread started')


def _loop():
    time.sleep(5)
    while True:
        try:
            from .sync import claim_next_job, process_job, schedule_maintenance
            schedule_maintenance()
            job = claim_next_job()
            if job:
                process_job(job)
            else:
                time.sleep(3)
        except Exception:
            logger.exception('Email worker loop error')
            time.sleep(5)
