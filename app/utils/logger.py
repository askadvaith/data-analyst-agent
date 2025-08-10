import os
import time
import uuid
from typing import Callable


class LogSession:
    """Lightweight file logger for per-request logs under <project>/logs.

    Use .log(text) to append lines. Thread-safe enough for this use (append-only).
    """

    def __init__(self, project_root: str | None = None, file_prefix: str | None = None):
        # LOGGING CODE: determine project root and ensure logs directory exists
        if project_root is None:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.project_root = project_root
        logs_dir = os.path.join(project_root, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        ts = time.strftime("%Y%m%d-%H%M%S")
        rid = uuid.uuid4().hex[:8]
        prefix = (file_prefix or "log")
        # LOGGING CODE: create unique log file path
        self.path = os.path.join(logs_dir, f"{prefix}-{ts}-{rid}.log")

        # LOGGING CODE: create the file early with a header
        self.log(f"Log session started: {time.ctime()} at {self.path}")

    def log(self, message: str) -> None:
        # LOGGING CODE: append timestamped message to the log file
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            # Swallow logging errors to avoid impacting API behavior
            pass


def new_log_session(project_root: str | None = None, file_prefix: str | None = None) -> LogSession:
    # LOGGING CODE: convenience factory for LogSession
    return LogSession(project_root=project_root, file_prefix=file_prefix)
