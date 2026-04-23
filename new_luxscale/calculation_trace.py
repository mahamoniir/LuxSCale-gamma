"""
Per-request step timing for /calculate — writes human-readable .txt under calculation_logs/.
"""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from luxscale.paths import project_root

LOG_DIR_NAME = "calculation_logs"


class CalculationTrace:
    """
    Records named steps with wall-clock deltas (time.perf_counter).
    Each row: step name, delta since previous step, cumulative since start, optional details.
    """

    def __init__(self, title: str = "calculate"):
        self.title = title
        self._t0 = time.perf_counter()
        self._last = self._t0
        self.rows: List[Tuple[str, float, float, Dict[str, Any]]] = []
        self.started_at = datetime.datetime.now().isoformat(timespec="seconds")

    def step(self, name: str, **detail: Any) -> None:
        now = time.perf_counter()
        delta = now - self._last
        cum = now - self._t0
        self._last = now
        self.rows.append((name, delta, cum, dict(detail)))

    def total_seconds(self) -> float:
        return time.perf_counter() - self._t0

    def as_text(self) -> str:
        lines = [
            "=" * 72,
            f"LuxScaleAI calculation trace — {self.title}",
            f"Started (local): {self.started_at}",
            "=" * 72,
            "",
            f"{'Step':<48} {'delta_s':>10} {'sum_s':>10}",
            "-" * 72,
        ]
        for name, delta, cum, det in self.rows:
            safe = (name or "")[:48]
            lines.append(f"{safe:<48} {delta:10.4f} {cum:10.4f}")
            if det:
                for k, v in sorted(det.items()):
                    lines.append(f"    {k}: {v}")
        lines.append("-" * 72)
        lines.append(f"{'TOTAL (wall)':<48} {self.total_seconds():10.4f}")
        lines.append("")
        return "\n".join(lines)

    def save(self, directory: Optional[str] = None) -> str:
        base = directory or os.path.join(project_root(), LOG_DIR_NAME)
        os.makedirs(base, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(base, f"calculation_steps_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.as_text())
        return path
