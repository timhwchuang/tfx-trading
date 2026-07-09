"""Post-trigger MAE/MFE windows (bar-based, 1m High/Low)."""

from __future__ import annotations

from typing import Any, Literal, Sequence

from storage.kbar_loader import KBarRecord

WINDOW_MINUTES = (15, 30, 60, 120)
Side = Literal["long", "short"]
FRICTION_POINTS_DEFAULT = 5.0


def enrich_post_trigger_windows(
    *,
    entry_price: float,
    entry_ts: int,
    bars_1m_after: Sequence[KBarRecord],
    atr: float,
    side: Side = "long",
    stop_ref: float | None = None,
    window_minutes: tuple[int, ...] = WINDOW_MINUTES,
) -> dict[str, Any]:
    """Signed MFE/MAE at fixed minute horizons.

    Long: MFE = max(High - entry), MAE = max(entry - Low).
    Short: MFE = max(entry - Low), MAE = max(High - entry).

    Also records stop_hit@30m / @60m if ``stop_ref`` is provided.
    Horizons with no bar data (e.g. night→day session gap) are simply omitted.
    """
    end_limit = entry_ts + max(window_minutes) * 60
    mfe = 0.0
    mae = 0.0
    out: dict[str, Any] = {"side": side}
    stop_hit_30 = False
    stop_hit_60 = False
    for bar in bars_1m_after:
        ts = int(bar.ts.timestamp())
        if ts < entry_ts:
            continue
        if ts > end_limit:
            break
        hi, lo = float(bar.High), float(bar.Low)
        if side == "long":
            mfe = max(mfe, hi - entry_price)
            mae = max(mae, entry_price - lo)
            if stop_ref is not None and lo <= stop_ref:
                elapsed = (ts - entry_ts) // 60
                if elapsed <= 30:
                    stop_hit_30 = True
                if elapsed <= 60:
                    stop_hit_60 = True
        else:
            mfe = max(mfe, entry_price - lo)
            mae = max(mae, hi - entry_price)
            if stop_ref is not None and hi >= stop_ref:
                elapsed = (ts - entry_ts) // 60
                if elapsed <= 30:
                    stop_hit_30 = True
                if elapsed <= 60:
                    stop_hit_60 = True
        elapsed_min = (ts - entry_ts) // 60
        for w in window_minutes:
            key = f"{w}m"
            if elapsed_min >= w and f"mfe_{key}" not in out:
                out[f"mfe_{key}"] = round(mfe, 2)
                out[f"mae_{key}"] = round(mae, 2)
                close = float(bar.Close)
                out[f"close_{key}"] = round(close, 1)
                if atr > 0:
                    out[f"mfe_{key}_atr"] = round(mfe / atr, 3)
                    out[f"mae_{key}_atr"] = round(mae / atr, 3)
    if stop_ref is not None:
        out["stop_hit_30m"] = stop_hit_30
        out["stop_hit_60m"] = stop_hit_60
    # Friction display proxy (not expectancy): gross path edge @60m minus round-trip friction.
    if "mfe_60m" in out and "mae_60m" in out:
        out["path_edge_60m"] = round(out["mfe_60m"] - out["mae_60m"], 2)
        out["path_edge_60m_net_friction5"] = round(
            out["mfe_60m"] - out["mae_60m"] - FRICTION_POINTS_DEFAULT, 2
        )
    return out
