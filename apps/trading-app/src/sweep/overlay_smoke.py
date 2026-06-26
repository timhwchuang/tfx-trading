"""FT-003: verify sweep grid keys are wired into RuntimeConfig (and KPI when applicable)."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

from core.runtime_config import SWEEP_FIELD_TO_CONST, default_runtime_config, normalize_overlay_key
from strategy_vwap_momentum import apply_strategy_params, restore_strategy_params
from sweep.param_sweep import _aggregate_kpi, _run_backtest_summaries
from sweep.holdout_guard import assert_dates_unsealed
from storage.tick_loader import DEFAULT_CACHE_DIR

# Execution / timing keys: overlay wiring is required; single-day KPI may be unchanged.
OVERLAY_SMOKE_KPI_OPTIONAL_KEYS = frozenset(
    {
        "pending_timeout_sec",
        "momentum_timeout_sec",
        "exit_grace_sec",
        "exit_grace_ticks",
        "ioc_slippage_points",
        "flatten_slippage_points",
        "max_consecutive_loss",
    }
)


def _canonical_snake_key(key: str) -> str:
    if key in SWEEP_FIELD_TO_CONST:
        return key
    upper = key.upper()
    for snake, const in SWEEP_FIELD_TO_CONST.items():
        if const == key or const == upper:
            return snake
    return key.lower()


def _read_applied_value(cfg: Any, key: str) -> Any:
    const = normalize_overlay_key(key)
    snake = _canonical_snake_key(key)
    return cfg.live_get(const, getattr(cfg, snake, None))


def _values_equal(expected: Any, actual: Any) -> bool:
    if actual == expected:
        return True
    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        return False


def _kpi_fingerprint(kpi: dict[str, Any]) -> str:
    subset = {
        "daily_pnl_points": kpi.get("daily_pnl_points"),
        "quick_stop_loss_rate": kpi.get("quick_stop_loss_rate"),
        "trade_count": kpi.get("trade_count"),
        "day_count": kpi.get("day_count"),
    }
    return json.dumps(subset, sort_keys=True)


def run_overlay_smoke(
    *,
    key: str,
    values: list[Any],
    date: datetime.date,
    code: str = "TMFR1",
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> int:
    if len(values) < 2:
        print("overlay_smoke: need at least two --values", file=sys.stderr)
        return 2

    assert_dates_unsealed([date])

    cache_path = Path(cache_dir)
    snake_key = _canonical_snake_key(key)
    fingerprints: list[str] = []
    applied_values: list[Any] = []

    for value in values:
        cfg = default_runtime_config()
        saved = apply_strategy_params({key: value}, cfg)
        try:
            applied = _read_applied_value(cfg, key)
            if not _values_equal(value, applied):
                print(
                    f"overlay_smoke FAIL: key {key!r} overlay readback "
                    f"expected {value!r} got {applied!r}",
                    file=sys.stderr,
                )
                return 1
            applied_values.append(applied)

            summaries, _, _ = _run_backtest_summaries(
                code, [date], cache_path, runtime_config=cfg
            )
            kpi = _aggregate_kpi(summaries)
            fingerprints.append(_kpi_fingerprint(kpi))
            print(f"value={value!r} applied={applied!r} kpi={fingerprints[-1]}")
        finally:
            restore_strategy_params(saved, cfg)

    if len(set(fingerprints)) >= 2:
        print(f"overlay_smoke PASS: key {key!r} affects KPI")
        return 0

    if snake_key in OVERLAY_SMOKE_KPI_OPTIONAL_KEYS and len(set(applied_values)) >= 2:
        print(
            f"overlay_smoke PASS: key {key!r} overlay verified "
            f"(KPI unchanged on smoke day — expected for execution/timing keys)"
        )
        return 0

    print(
        f"overlay_smoke FAIL: key {key!r} did not change KPI across values {values}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "FT-003: verify a sweep overlay key is wired into RuntimeConfig; "
            "prefer KPI change on one day, else overlay readback for timing keys"
        )
    )
    parser.add_argument("--key", required=True, help="grid.json key (snake_case)")
    parser.add_argument(
        "--values",
        nargs="+",
        required=True,
        help="At least two values to compare (numbers parsed when possible)",
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD trading day")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    args = parser.parse_args(argv)

    parsed_values: list[Any] = []
    for raw in args.values:
        try:
            if "." in raw:
                parsed_values.append(float(raw))
            else:
                parsed_values.append(int(raw))
        except ValueError:
            if raw.lower() in ("true", "false"):
                parsed_values.append(raw.lower() == "true")
            else:
                parsed_values.append(raw)

    return run_overlay_smoke(
        key=args.key,
        values=parsed_values,
        date=datetime.date.fromisoformat(args.date),
        code=args.code,
        cache_dir=args.cache_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
