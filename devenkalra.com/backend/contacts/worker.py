"""In-process background loop that executes queued sync runs, one at a time."""
import logging
import sys
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()
SERVERS = ('gunicorn', 'runserver', 'uvicorn', 'daphne')


def start_worker_thread():
    global _started
    with _lock:
        if _started or not any(s in ' '.join(sys.argv) for s in SERVERS):
            return
        threading.Thread(target=_loop, name='contacts-sync-worker', daemon=True).start()
        _started = True
        logger.info('Contacts sync worker thread started')


def _loop():
    time.sleep(5)
    while True:
        try:
            from .runner import claim, execute_run, recover_stale
            recover_stale()
            run = claim()
            if run:
                execute_run(run)
            else:
                time.sleep(3)
        except Exception:
            logger.exception('Contacts worker loop error')
            time.sleep(5)
