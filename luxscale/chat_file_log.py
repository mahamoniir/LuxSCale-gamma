"""
Append-only JSON-per-line chat audit log, one file per ISO week under ``logs/chat/``,
with automatic deletion of log files older than 7 days.

Used by the Flask /api/chat/* routes. View with ``tools/print_chat_log.py`` or
``print_chat_log.php`` (local / token only).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from luxscale.paths import project_root

# --- retention: drop *.log in logs/chat/ when mtime older than this -----------------
_RETENTION_SEC = 7 * 24 * 3600
# Purge at most once per this interval to avoid I/O on every request
_PURGE_MIN_INTERVAL = 3600.0
_last_purge: float = 0.0
_purge_lock = threading.Lock()


def _week_file_suffix(d: date | None = None) -> str:
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f"{y}_W{w:02d}"


def chat_log_dir() -> str:
    return os.path.join(project_root(), "logs", "chat")


def current_weekly_log_path() -> str:
    return os.path.join(chat_log_dir(), f"chat_{_week_file_suffix()}.log")


def _ensure_dir() -> str:
    d = chat_log_dir()
    os.makedirs(d, exist_ok=True)
    return d


def purge_stale_chat_logs() -> int:
    """Remove ``logs/chat/*.log`` files with mtime older than 7 days. Returns deleted count."""
    d = chat_log_dir()
    if not os.path.isdir(d):
        return 0
    now = time.time()
    n = 0
    for name in os.listdir(d):
        if not name.endswith(".log"):
            continue
        path = os.path.join(d, name)
        try:
            if now - os.path.getmtime(path) > _RETENTION_SEC:
                os.remove(path)
                n += 1
        except OSError:
            continue
    return n


def _maybe_purge() -> None:
    global _last_purge
    t = time.time()
    if t - _last_purge < _PURGE_MIN_INTERVAL:
        return
    with _purge_lock:
        if t - _last_purge < _PURGE_MIN_INTERVAL:
            return
        _last_purge = t
    try:
        purge_stale_chat_logs()
    except OSError:
        pass


def init_chat_file_logging() -> None:
    """Create log directory; run an initial retention sweep."""
    _ensure_dir()
    purge_stale_chat_logs()


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").replace("\r", " ")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def append_chat_event(
    *,
    event: str,
    ip: str = "",
    session_id: str = "",
    user_id: str = "",
    message: str = "",
    status: str = "ok",
    source: str = "",
    err: str = "",
    http_status: int = 0,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    _maybe_purge()
    _ensure_dir()
    path = current_weekly_log_path()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "ip": ip,
        "session_id": (session_id or "")[:200],
        "user_id": (user_id or "")[:120],
        "message_len": len(message),
        "message_preview": _truncate(message, 400),
        "status": status,
        "source": (source or "")[:80],
        "err": (err or "")[:500] if err else "",
        "http": http_status,
    }
    if extra:
        record["extra"] = extra
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def list_chat_log_files() -> list[str]:
    """Newest mtime first."""
    d = chat_log_dir()
    if not os.path.isdir(d):
        return []
    out: list[tuple[float, str]] = []
    for name in os.listdir(d):
        if not name.startswith("chat_") or not name.endswith(".log"):
            continue
        p = os.path.join(d, name)
        if os.path.isfile(p):
            try:
                out.append((os.path.getmtime(p), p))
            except OSError:
                continue
    out.sort(key=lambda x: -x[0])
    return [p for _, p in out]


def read_chat_log_tail(file_path: str, max_lines: int = 200) -> str:
    if not os.path.isfile(file_path) or max_lines < 1:
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""
    chunk = lines[-max_lines:]
    return "".join(chunk)
