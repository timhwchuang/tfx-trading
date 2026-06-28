---
id: FT-013
slug: supertrend-flip
status: MVPClosed
thesis_class: mean_robust
proposal_id: P-007
opened: 2026-06-28
closed: 2026-06-28
outcome: stf_fingerprint_fail
phases: [0]
blockers: []
---

# FT-013 — SuperTrend Flip Continuation（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.1 · **診斷順序**：§5.2  
> **結案**：[`gate_report.md`](../../../workspaces/stf-baseline/gate_report.md) · `stf_fingerprint_fail` · train W30 med **−10.0**

## Phase 0a — Counterfactual（不得跑 train）

- [x] SPEC + PLAN（本檔）
- [x] `reporting/supertrend_flip_counterfactual.py`（`compute_supertrend_v1` · MUST-1/2/3 · funnel · post_entry hook）
- [x] `scripts/ft013_stf_counterfactual.py`（`--fingerprint-only` · `--grid` 子命令或旗標）
- [x] `tests/reporting/test_supertrend_flip_counterfactual.py`（見 **§ 優先測試**）
- [x] SPEC §3 / §5.0b / §5.1a 與程式逐條對照

### 優先測試（Phase 0a · 對照 SPEC）

| # | Case | 狀態 |
|---|------|------|
| 1 | partial 5m bar **不**產生 flip | ok |
| 2 | flip 在 bar **收盤後**；**第一個** `tick.close > ST line` 才 entry | ok |
| 3 | cooldown 內第二次 long flip **忽略** | ok |
| 4 | **11:45** / **12:00** session 邊界各一 case | ok |
| 5 | `compute_supertrend_v1` ratchet + **SMA(TR)** fixture | ok |
| 6 | payload 含 `slippage_ratio`（MUST-2） | ok |
| 7 | exit = `simulate_atr_barrier_exit` · `atr_effective` 同 ST | ok |
| 8 | `entry_fill = entry_price + 1` · `flip_short` post_entry only | ok |

## Phase 0b — Code review（MUST 先於 train）

- [x] Agent MUST 對照 review PASS（2026-06-28 · 見 gate_report §0b）
- [x] **MUST-1** 無 repaint · flip 確認 tick · **atr_series_from_bars** · ORB slice 索引
- [x] **MUST-2** 摩擦 5 內建 · slippage_ratio 附錄
- [x] **MUST-3** long-only · cooldown · 11:45/12:00 窗 · funnel 階段
- [x] **§5.2** fingerprint 與 grid 路徑分離

## Phase 0c — Train 2025（**兩段 · 禁止跳步**）

### 0c-1 Fingerprint — **未過 · 2026-06-28**

| 指標 | 值 |
|------|-----|
| n | 67 |
| W30 stop-less gross median | **−10.0** |
| barrier gross/趟 | −2.36 |
| 結案 | **MVPClosed** · 不跑 0c-2 |

```bash
cd apps/trading-app/src
python scripts/ft013_stf_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

### 0c-2 Grid — **跳過**（0c-1 未過）

## 產物（`workspaces/stf-baseline/`）

| 檔案 | 內容 |
|------|------|
| `gate_report.md` | 0b + 0c-1 結案敘事 |
| `reports/counterfactual_stf_fingerprint.json` | train 2025 fingerprint |
| `reports/counterfactual_stf_valid.json` | valid 2026 Q1 參考 |
| ~~`counterfactual_stf_train.json`~~ | 未產（grid 跳過） |

## Phase 1 — Plugin

- [ ] **取消** — MVPClosed
