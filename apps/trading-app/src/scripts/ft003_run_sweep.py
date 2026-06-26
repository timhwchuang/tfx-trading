"""FT-003: run param_sweep for one workspace agent with durable progress.

Fixed outputs (per agent workspace):
  workspaces/<agent>/logs/sweep_progress.log  — JSONL events + heartbeat
  workspaces/<agent>/logs/sweep.lock          — single-instance lock (do not remove while running)
  workspaces/<agent>/sweep_result.jsonl       — one combo per line (incremental; sorted at end)

Do NOT redirect stdout/stderr to sweep_progress.log — the tracker writes JSONL directly.

Default mode is bulk (one BacktestEngine per train/valid phase). Use ``--per-day`` for finer
per-day progress at the cost of much longer runtime.

If the process is hard-killed (Task Manager, terminal closed), progress may stop mid-combo with
no ``sweep_failed`` line. Check the last JSONL ``event`` and whether ``logs/sweep.lock`` remains
(stale locks are replaced on the next run when the PID is dead).

``sweep_result.jsonl`` lines are appended in **completion order** during the run; the file is
re-sorted by ``valid_score`` only after ``sweep_done``. Do not treat a partial file as ranking.
"""

from __future__ import annotations

import os
import sys
import traceback

# Quiet engine DECISION_AUDIT flood during multi-day sweep.
os.environ.setdefault("LOG_LEVEL", "ERROR")

import argparse
import json
import logging
from pathlib import Path

from storage.tick_loader import resolve_cli_tick_cache_dates
from sweep.param_sweep import assert_sweep_has_runnable_combos, sweep, validate_sweep_inputs
from sweep.sweep_instance_lock import SweepInstanceLock
from sweep.sweep_progress import MIN_HEARTBEAT_SEC, SweepProgressTracker

# Heartbeat interval (seconds) during long bulk phases.
DEFAULT_HEARTBEAT_SEC = 60.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _workspace_paths(root: Path, agent: str) -> tuple[Path, Path, Path]:
    ws = root / "workspaces" / agent
    progress = ws / "logs" / "sweep_progress.log"
    results = ws / "sweep_result.jsonl"
    lock = ws / "logs" / "sweep.lock"
    return progress, results, lock


def _parse_heartbeat_sec(value: str) -> float:
    sec = float(value)
    if sec < MIN_HEARTBEAT_SEC:
        raise argparse.ArgumentTypeError(
            f"heartbeat interval must be >= {MIN_HEARTBEAT_SEC:g} seconds"
        )
    return sec


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="FT-003 param_sweep for one agent workspace")
    parser.add_argument("agent", help="workspace slug, e.g. agent-conservative")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument(
        "--per-day",
        action="store_true",
        help="split each train/valid phase into per-day engine runs (slower, emits day events)",
    )
    parser.add_argument(
        "--heartbeat-sec",
        type=_parse_heartbeat_sec,
        default=DEFAULT_HEARTBEAT_SEC,
        metavar="SEC",
        help=(
            f"progress heartbeat interval during bulk phases "
            f"(default {DEFAULT_HEARTBEAT_SEC:g}, min {MIN_HEARTBEAT_SEC:g})"
        ),
    )
    args = parser.parse_args(argv)
    bulk_days = not args.per_day

    root = _repo_root()
    agent = args.agent
    grid_path = root / "workspaces" / agent / "grid.json"
    if not grid_path.is_file():
        print(f"FAILED exit=1 missing {grid_path}", file=sys.stderr)
        return 1

    progress_path, result_path, lock_path = _workspace_paths(root, agent)
    lock = SweepInstanceLock(lock_path)
    try:
        lock.acquire()
    except RuntimeError as exc:
        print(f"FAILED exit=2 {exc}", file=sys.stderr)
        return 2

    tracker = SweepProgressTracker(
        progress_path,
        result_path,
        heartbeat_sec=args.heartbeat_sec,
    )

    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    cache = root / "tick_cache"
    train = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=args.code,
        cache_dir=cache,
        from_date="2026-01-01",
        to_date="2026-03-31",
    )
    valid = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=args.code,
        cache_dir=cache,
        from_date="2026-04-01",
        to_date="2026-04-30",
    )

    exit_code = 0
    sweep_started = False
    try:
        validate_sweep_inputs(grid, train, valid)
        assert_sweep_has_runnable_combos(grid)
        tracker.start_sweep(
            agent=agent,
            code=args.code,
            train_days=len(train),
            valid_days=len(valid),
            grid_keys=list(grid.keys()),
            bulk_days=bulk_days,
            progress_path=str(progress_path),
            result_path=str(result_path),
        )
        sweep_started = True

        print(f"SWEEP_START agent={agent} progress={progress_path} results={result_path}")

        rows = sweep(
            grid,
            train,
            valid,
            code=args.code,
            cache_dir=cache,
            output_path=result_path,
            progress=tracker,
            bulk_days=bulk_days,
        )

        top_score = rows[0].get("valid_score") if rows else None
        top_params = rows[0].get("params") if rows else None
        tracker.finish(
            "DONE",
            exit_code=0,
            top_valid_score=top_score,
            top_params=top_params,
        )
        print(
            f"DONE exit=0 agent={agent} combos={len(rows)} "
            f"top_valid_score={top_score} top_params={top_params}"
        )
        print(f"progress={progress_path}")
        print(f"results={result_path}")
    except KeyboardInterrupt:
        if sweep_started:
            tracker.finish("FAILED", exit_code=130, error="KeyboardInterrupt")
        print("FAILED exit=130 interrupted", file=sys.stderr)
        print(f"progress={progress_path}", file=sys.stderr)
        exit_code = 130
    except Exception as exc:
        if sweep_started:
            tracker.finish(
                "FAILED",
                exit_code=1,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
        print(f"FAILED exit=1 agent={agent} error={exc}", file=sys.stderr)
        print(f"progress={progress_path}", file=sys.stderr)
        exit_code = 1
    finally:
        lock.release()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
