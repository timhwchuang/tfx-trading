---
id: FT-013
slug: supertrend-flip
status: InProgress
thesis_class: mean_robust
proposal_id: P-007
opened: 2026-06-28
phases: [0]
blockers: []
---

# FT-013 — SuperTrend Flip Continuation（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.1 · **診斷順序**：§5.2

## Phase 0a — Counterfactual（不得跑 train）

- [x] SPEC + PLAN（本檔）
- [ ] `reporting/supertrend_flip_counterfactual.py`（`compute_supertrend_v1` · MUST-1/2/3 · funnel · post_entry hook）
- [ ] `scripts/ft013_stf_counterfactual.py`（`--fingerprint-only` · `--grid` 子命令或旗標）
- [ ] `tests/reporting/test_supertrend_flip_counterfactual.py`（見 **§ 優先測試**）
- [ ] SPEC §3 / §5.0b / §5.1a 與程式逐條對照

### 優先測試（Phase 0a · 對照 SPEC）

| # | Case |
|---|------|
| 1 | partial 5m bar **不**產生 flip |
| 2 | flip 在 bar **收盤後**；**第一個** `tick.close > ST line` 才 entry |
| 3 | cooldown 內第二次 long flip **忽略** |
| 4 | **11:45** / **12:00** session 邊界各一 case |
| 5 | `compute_supertrend_v1` ratchet + **SMA(TR)** fixture 與手算一致（非 TV Wilder ATR） |
| 6 | payload 含 `slippage_ratio`（MUST-2） |
| 7 | exit = `simulate_atr_barrier_exit` · `atr_effective` 同 ST（§5.0b） |
| 8 | `entry_fill = entry_price + 1`（Long）· `min_atr=25` floor · `flip_short` post_entry only |

## Phase 0b — Code review（MUST 先於 train）

- [ ] Bugbot 或人類 review PASS
- [ ] **MUST-1** 無 repaint · flip 確認 tick · **atr_series_from_bars**（非 Wilder）
- [ ] **MUST-2** 摩擦 5 內建 · slippage_ratio 附錄
- [ ] **MUST-3** long-only · cooldown · 11:45/12:00 窗 · funnel 階段
- [ ] **§5.2** fingerprint 與 grid 路徑分離

## Phase 0c — Train 2025（**兩段 · 禁止跳步**）

### 0c-1 Fingerprint（**先跑 · 單點參數**）

凍結：`atr_period=10` · `st_mult=3.0` · `cooldown_bars=6` · `k_sl=1.0` · **`tp_atr_k=2.0`** · long-only  
**Exit（封印）**：`simulate_atr_barrier_exit(hard_stop_atr_k=1.0, tp_atr_k=2.0, max_hold_sec=180)` · variant **`atr_barrier_180s`**

```bash
cd apps/trading-app/src
python scripts/ft013_stf_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

**通過線（0c-1）**：n≥30 · **W30 stop-less gross median > 0** · funnel 可解讀  

**0c-1 未過**（W30≤0 或 n<30）→ **MVPClosed** · **不跑 0c-2**

> **cache_audit**：預設跳過 — 見 [`CACHE_AUDIT.md`](../../../workspaces/CACHE_AUDIT.md)；backfill 後增量掃即可。

### 0c-2 Grid（**僅** 0c-1 通過後）

```bash
python scripts/ft013_stf_counterfactual.py --cache-dir ../../../tick_cache --grid
```

**0c-2 未過**（G1/G2/G3 或 §3.1）→ **MVPClosed**（`stf_fingerprint_pass_g1_fail` 若 fingerprint 已過、grid mean gross≤5）

## 產物（`workspaces/stf-baseline/`）

| 檔案 | 內容 |
|------|------|
| `gate_report.md` | `## Fingerprint (0c-1)` · `## Grid (0c-2)` · G1–G3 · §3.1 · slippage_ratio · valid |
| `reports/counterfactual_stf_fingerprint.json` | 單點 · funnel · post_entry |
| `reports/counterfactual_stf_train.json` | grid · Long · post_entry_by_* |

## Phase 1 — Plugin（train 過 + 人類 Go 後）

- [ ] `packages/strategies/supertrend-flip/`
- [ ] baseline replay valid Q1

## Workspace

```
workspaces/stf-baseline/
  gate_report.md
  reports/counterfactual_stf_fingerprint.json
  reports/counterfactual_stf_train.json
```
