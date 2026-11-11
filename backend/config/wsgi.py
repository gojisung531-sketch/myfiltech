import os
import threading
import time

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()


def _start_worker():
    import logging
    from django.db import close_old_connections
    from apps.core.jobs import Job, run_once

    logger = logging.getLogger("worker")

    def _loop():
        time.sleep(3)  # wait for startup
        try:
            # Reset any stuck RUNNING jobs from server restart
            Job.objects.filter(status=Job.Status.RUNNING).update(status=Job.Status.PENDING, attempts=0)
        except Exception:
            pass

        while True:
            try:
                close_old_connections()
                ran = run_once()
                if not ran:
                    time.sleep(2)
            except Exception as e:
                logger.exception("Worker thread error: %s", e)
                time.sleep(3)

    t = threading.Thread(target=_loop, daemon=True, name="bg_job_worker")
    t.start()


_start_worker()
