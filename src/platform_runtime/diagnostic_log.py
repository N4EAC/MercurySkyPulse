"""Bounded, redacted persistent diagnostics for field-test support."""

from __future__ import annotations

from logging import Formatter, Logger
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import sys
import threading
import time
import traceback
from uuid import uuid4


_SECRET = re.compile(
    r"(?i)\b(password|passwd|proof|verifier|secret|token)\b(\s*[:=]\s*)([^\s,;]+)"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DiagnosticLog:
    """Write UTF-8 diagnostics with immediate flush and bounded rotation."""

    def __init__(self, path: Path, *, max_bytes: int = 10 * 1024 * 1024,
                 backup_count: int = 10, maximum_message_chars: int = 32_768) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.maximum_message_chars = maximum_message_chars
        self.session_id = uuid4().hex[:12]
        self._logger = Logger(f"mercuryskypulse.{self.session_id}")
        self._logger.setLevel(10)
        self._logger.propagate = False
        self._handler = RotatingFileHandler(
            self.path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        formatter = Formatter(
            "%(asctime)sZ | %(levelname)s | %(message)s", "%Y-%m-%dT%H:%M:%S"
        )
        formatter.converter = time.gmtime
        self._handler.setFormatter(formatter)
        self._logger.addHandler(self._handler)
        self._previous_sys_hook = None
        self._previous_thread_hook = None

    def start_session(self, application_version: str) -> None:
        self.write(
            "runtime", "session_start", version=application_version,
            session=self.session_id, pid=os.getpid(), platform=platform.platform(),
            architecture=platform.machine(), python=platform.python_version(),
            frozen=bool(getattr(sys, "frozen", False)), executable=sys.executable,
        )

    def write_activity(self, message: str) -> None:
        self._write("INFO", f"component=activity event=line message={message}")

    def write(self, component: str, event: str, **fields: object) -> None:
        details = " ".join(
            f"{key}={self._field(value)}" for key, value in sorted(fields.items())
        )
        prefix = f"component={component} event={event}"
        self._write("INFO", f"{prefix} {details}" if details else prefix)

    def install_exception_hooks(self) -> None:
        self._previous_sys_hook = sys.excepthook
        self._previous_thread_hook = getattr(threading, "excepthook", None)

        def sys_hook(exc_type, value, tb) -> None:
            self._write_exception("main_thread", exc_type, value, tb)
            if self._previous_sys_hook:
                self._previous_sys_hook(exc_type, value, tb)

        def thread_hook(args) -> None:
            name = args.thread.name if args.thread else "unknown"
            self._write_exception(
                f"thread:{name}", args.exc_type, args.exc_value, args.exc_traceback
            )
            if self._previous_thread_hook:
                self._previous_thread_hook(args)

        sys.excepthook = sys_hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = thread_hook

    def close(self) -> None:
        self.write("runtime", "session_end", session=self.session_id)
        if self._previous_sys_hook is not None:
            sys.excepthook = self._previous_sys_hook
        if self._previous_thread_hook is not None and hasattr(threading, "excepthook"):
            threading.excepthook = self._previous_thread_hook
        self._handler.flush()
        self._handler.close()
        self._logger.removeHandler(self._handler)

    def _write_exception(self, origin, exc_type, value, tb) -> None:
        rendered = "".join(traceback.format_exception(exc_type, value, tb))
        self._write(
            "ERROR",
            f"component=runtime event=uncaught_exception origin={origin} traceback={rendered}",
        )

    def _write(self, level: str, message: str) -> None:
        clean = _CONTROL.sub("?", str(message)).replace("\r", "\\r").replace("\n", "\\n")
        clean = _SECRET.sub(
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", clean
        )
        if len(clean) > self.maximum_message_chars:
            clean = clean[: self.maximum_message_chars] + "…[truncated]"
        self._logger.log(40 if level == "ERROR" else 20, clean)
        self._handler.flush()

    @staticmethod
    def _field(value: object) -> str:
        return repr(str(value))
