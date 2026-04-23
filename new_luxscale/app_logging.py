"""
Central step logging for LuxScaleAI (file + console).
Log file: ``luxscale_app.log`` at repository root.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from luxscale.paths import project_root

_LOG_DIR = project_root()
LOG_FILE = os.path.join(_LOG_DIR, "luxscale_app.log")

_logger: Optional[logging.Logger] = None


def _setup() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    lg = logging.getLogger("luxscale")
    lg.setLevel(logging.INFO)
    if lg.handlers:
        _logger = lg
        return lg
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    lg.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(sh)
    _logger = lg
    return lg


def log_step(step: str, result=None, **detail) -> None:
    lg = _setup()
    parts = [f"STEP: {step}"]
    if result is not None:
        try:
            parts.append(f"RESULT: {result!r}")
        except Exception:
            parts.append("RESULT: <unprintable>")
    if detail:
        try:
            parts.append("DETAIL: " + json.dumps(detail, ensure_ascii=False, default=str))
        except Exception:
            parts.append(f"DETAIL: {detail!r}")
    lg.info(" | ".join(parts))


def log_exception(step: str, exc: BaseException) -> None:
    lg = _setup()
    lg.error("STEP: %s | EXCEPTION: %s", step, exc, exc_info=exc)
