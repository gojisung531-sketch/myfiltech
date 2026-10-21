import signal
import threading
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core.app_settings import get_setting
from apps.core.jobs import run_once

POLL_INTERVAL_SEC = 2


class Command(BaseCommand):
    help = "Run the background job worker (specs/01 §5)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process pending jobs, then exit.")
        parser.add_argument(
            "--concurrency", type=int, default=None, help="Override jobs.concurrency."
        )

    def handle(self, *args, once=False, concurrency=None, **options):
        if once:
            count = 0
            while run_once():
                count += 1
            self.stdout.write(f"Processed {count} job(s).")
            return

        workers = concurrency or get_setting("jobs.concurrency") or 1
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())

        def loop():
            while not stop.is_set():
                close_old_connections()  # long-running thread: drop stale/broken connections
                if not run_once():
                    stop.wait(POLL_INTERVAL_SEC)
            close_old_connections()

        threads = [threading.Thread(target=loop, daemon=True) for _ in range(workers)]
        for thread in threads:
            thread.start()
        self.stdout.write(f"Job worker started with {workers} thread(s). Ctrl+C to stop.")
        while not stop.is_set():
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=30)
        self.stdout.write("Job worker stopped.")
