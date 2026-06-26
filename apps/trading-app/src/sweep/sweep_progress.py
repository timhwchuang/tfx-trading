"""Incremental progress + heartbeat for long param_sweep runs (FT-003)."""

from __future__ import annotations

import datetime
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_DEFAULT_HEARTBEAT_SEC = 60.0
MIN_HEARTBEAT_SEC = 5.0


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class SweepProgressTracker:
    """Append-only progress log + incremental sweep_result.jsonl writes.

    Fixed paths (typically under ``workspaces/<agent>/``) are owned by the caller
    (``ft003_run_sweep``). Each completed combo appends one result line immediately.
    """

    def __init__(
        self,
        progress_path: Path,
        result_path: Path,
        *,
        heartbeat_sec: float = _DEFAULT_HEARTBEAT_SEC,
    ) -> None:
        self.progress_path = Path(progress_path)
        self.result_path = Path(result_path)
        self.heartbeat_sec = heartbeat_sec
        self._state: dict[str, Any] = {"event": "idle"}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._combos_completed = 0
        self._combos_skipped = 0
        self._phase_started_at: float | None = None
        self.run_id: str = ""

    def start_sweep(self, **meta: Any) -> None:
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self.progress_path.write_text("", encoding="utf-8")
            self.result_path.write_text("", encoding="utf-8")
        self._combos_completed = 0
        self._combos_skipped = 0
        self._append_progress("sweep_start", run_id=self.run_id, **meta)
        self._stop.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def combo_skipped(
        self,
        combo_index: int,
        combo_total: int,
        params: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        with self._lock:
            self._combos_skipped += 1
            combos_skipped = self._combos_skipped
        self._append_progress(
            "combo_skipped",
            combo_index=combo_index,
            combo_total=combo_total,
            combos_skipped=combos_skipped,
            params=params,
            reason=reason,
        )

    def combo_start(
        self,
        combo_index: int,
        combo_total: int,
        params: dict[str, Any],
        *,
        run_index: int,
        run_total: int,
        train_days: int,
        valid_days: int,
    ) -> None:
        with self._lock:
            self._state = {
                "combo_index": combo_index,
                "combo_total": combo_total,
                "run_index": run_index,
                "run_total": run_total,
                "phase": "train",
                "day_index": 0,
                "day_total": train_days,
                "date": None,
                "params": params,
            }
        self._append_progress(
            "combo_start",
            combo_index=combo_index,
            combo_total=combo_total,
            run_index=run_index,
            run_total=run_total,
            train_days=train_days,
            valid_days=valid_days,
            params=params,
        )

    def phase_start(self, phase: str, *, day_total: int) -> None:
        with self._lock:
            self._state["phase"] = phase
            self._state["day_index"] = 0
            self._state["day_total"] = day_total
            self._state["date"] = None
            self._phase_started_at = time.monotonic()
            combo_index = self._state.get("combo_index")
            combo_total = self._state.get("combo_total")
        self._append_progress(
            "phase_start",
            combo_index=combo_index,
            combo_total=combo_total,
            phase=phase,
            day_total=day_total,
            phase_elapsed_sec=0.0,
        )

    def day_complete(
        self,
        day_index: int,
        day_total: int,
        date: datetime.date,
        phase: str,
    ) -> None:
        with self._lock:
            self._state.update(
                {
                    "phase": phase,
                    "day_index": day_index,
                    "day_total": day_total,
                    "date": date.isoformat(),
                }
            )
            snap = dict(self._state)
        self._append_progress(
            "day",
            combo_index=snap.get("combo_index"),
            combo_total=snap.get("combo_total"),
            phase=phase,
            day_index=day_index,
            day_total=day_total,
            date=date.isoformat(),
        )

    def combo_done(self, row: dict[str, Any]) -> None:
        slim = slim_sweep_row(row)
        line = json.dumps(slim, ensure_ascii=False) + "\n"
        with self._lock:
            with self.result_path.open("a", encoding="utf-8") as f:
                f.write(line)
            self._combos_completed += 1
            snap = dict(self._state)
            combos_completed = self._combos_completed
        self._append_progress(
            "combo_done",
            combo_index=snap.get("combo_index"),
            combo_total=snap.get("combo_total"),
            run_index=snap.get("run_index"),
            run_total=snap.get("run_total"),
            combos_completed=combos_completed,
            valid_score=row.get("valid_score"),
            params=row.get("params"),
        )

    def finish(self, status: str, *, exit_code: int, **meta: Any) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.heartbeat_sec + 5)
        event = "sweep_done" if exit_code == 0 else "sweep_failed"
        fields = dict(meta)
        fields.setdefault("combos_completed", self._combos_completed)
        fields.setdefault("combos_skipped", self._combos_skipped)
        self._append_progress(
            event,
            status=status,
            exit_code=exit_code,
            **fields,
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_sec):
            self._append_progress("heartbeat", **self._snapshot_locked())

    def _snapshot_locked(self) -> dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
            if self._phase_started_at is not None:
                snap["phase_elapsed_sec"] = round(
                    time.monotonic() - self._phase_started_at, 1
                )
            return snap

    def _append_progress(self, event: str, **fields: Any) -> None:
        record = {"ts": _now_iso(), "event": event, **fields}
        if self.run_id and event != "sweep_start":
            record.setdefault("run_id", self.run_id)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            self.progress_path.parent.mkdir(parents=True, exist_ok=True)
            with self.progress_path.open("a", encoding="utf-8") as f:
                f.write(line)


def slim_sweep_row(row: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky ``_summaries`` from KPI blobs before persisting jsonl."""
    out = dict(row)
    for key in ("train_kpi", "valid_kpi"):
        kpi = out.get(key)
        if isinstance(kpi, dict):
            out[key] = {k: v for k, v in kpi.items() if k != "_summaries"}
    return out
