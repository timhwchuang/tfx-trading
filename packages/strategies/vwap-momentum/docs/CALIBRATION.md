# P6-1 Trend Filter Calibration

> **Owner**: `strategy-vwap-momentum`  
> **App orchestration**: [trading-app SWEEP_SPEC](https://github.com/timhwchuang/trading-app/blob/main/docs/SWEEP_SPEC.md)  
> **B-class tooling**: `trading-app` `python -m reporting.calibration_cli` (log + tick_cache replay)  
> **Human gate**: CAL-8 Go/No-Go still requires ≥5 UAT days of real ticks + sign-off

Workflow for calibrating `trend_min_strength` and related flags **before** enabling `trend_filter_enabled` in production config.

---

## Iron rules

- `trend_filter_enabled` defaults **`false`**
- `trend_min_strength=0.0` is **strictest** (most vetoes), not permissive
- No flag changes without harness evidence + human Go/No-Go
- A-class (1～5) complete with synthetic tests only; B-class needs real UAT logs

---

## Workflow (CAL-5 SOP)

### 1. Accumulate

- UAT: `TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1`
- Target ≥5–10 trading days with ticks + kbars + `SIGNAL_AUDIT` (including `reason=trend_veto`)

### 2. Harness (CAL-2)

**CLI (B-class, recommended)**:

```powershell
cd trading-app
python -m reporting.calibration_cli logs/uat.log `
  --dates 2026-06-10,2026-06-11,2026-06-12 `
  --cache-dir tick_cache `
  --forward-seconds 1800
```

**Library**:

```python
from reporting.trend_calibration import run_b_class_calibration
from reporting.forward_pnl import ForwardPnlPolicy

run_b_class_calibration(
    log_paths=[Path("logs/uat.log")],
    code="TXFR1",
    dates=[...],
    forward_policy=ForwardPnlPolicy(window_seconds=1800),
)
```

Outputs: `veto_rate`, `delta_expectancy`, `forward_policy`, tick count.

- A-class: synthetic scenarios in `tests/reporting/test_trend_calibration.py`
- B-class: `reporting/forward_pnl.py` tick replay → real `get_forward_pnl`

### 3. Sweep (CAL-3)

```powershell
python -m reporting.calibration_cli logs/uat.log `
  --dates 2026-06-10,2026-06-11,2026-06-12 `
  --sweep --sweep-output sweep_result.jsonl
```

Or `sweep.param_sweep.sweep(..., forward_policy=ForwardPnlPolicy(...))` — when `forward_policy` is set and tick_cache exists, `veto_metrics.delta_expectancy` uses replay (not toy 0).

Default `trend_min_strength` grid: 0.0, 0.3, 0.5, 0.8, 1.0, 1.5 (ATR units).

Sort by valid-set survival KPI (net expectancy, MDD penalty); veto metrics are advisory.

### 4. Human Go/No-Go (CAL-8)

**Go**: stable positive `delta_expectancy`, reasonable `veto_rate`, net expectancy neutral or better.

**No-Go**: keep `trend_filter_enabled=false` and `min_strength=0.0`.

Record decision in `WeeklyStatus.md` with harness output paths.

---

## Strategy-side implementation notes

| Topic | Location |
|-------|----------|
| `compute_trend`, Level-2 gate | `src/strategy_vwap_momentum/trend.py` |
| `trend_allows_entry`, veto audit | `strategy.py` `_try_pullback_entry` |
| `StrategyParams` + sweep patch | `params.py` |
| Exchange-day slice guard | `tests/test_trend.py` CAL-1 regression |

### Sweep param patching (6.6)

Decision reads `StrategyParams.from_config()` — sweep must patch config namespace and restore after grid run. See app `SWEEP_SPEC.md`.

---

## Acceptance

| Class | Status | Tests |
|-------|--------|-------|
| A (1～5) | ✅ | `test_trend.py`, `test_evaluate_pure.py` (`test_trend_veto_emits_signal_audit_*`), app `test_trend_calibration.py` |
| B (6～8) | ✅ tooling / ☐ UAT data | `calibration_cli` + replay sweep; human Go/No-Go after ≥5 UAT days |

---

## Related

- [SPEC.md](../SPEC.md) §6 Trend Filter semantics
- [trading-engine STRATEGY.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/STRATEGY.md)