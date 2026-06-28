---
id: FT-013
slug: supertrend-flip
status: Draft
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
- [ ] `reporting/supertrend_flip_counterfactual.py`（含 MUST-1/2/3 · funnel · post_entry hook）
- [ ] `scripts/ft013_stf_counterfactual.py`（`--fingerprint-only` · `--grid` 子命令或旗標）
- [ ] `tests/reporting/test_supertrend_flip_counterfactual.py`（partial bar · flip confirm tick · cooldown · 12:00 block）
- [ ] SPEC §3 / §5.1 與程式逐條對照

## Phase 0b — Code review（MUST 先於 train）

- [ ] Bugbot 或人類 review PASS
- [ ] **MUST-1** 無 repaint · flip 確認 tick = 收盤後首 tick
- [ ] **MUST-2** 摩擦 5 內建 · slippage_ratio 附錄
- [ ] **MUST-3** long-only · cooldown · 11:45/12:00 窗 · funnel 階段
- [ ] **§5.2** fingerprint 與 grid 路徑分離

## Phase 0c — Train 2025（**兩段 · 禁止跳步**）

### 0c-1 Fingerprint（**先跑 · 單點參數**）

凍結：`atr_period=10` · `st_mult=3.0` · `cooldown_bars=6` · `k_sl=1.0` · long-only

```bash
cd apps/trading-app/src
python scripts/ft013_stf_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

**通過線**：n≥30 · **W30 stop-less gross median > 0** · funnel 可解讀  
**未過** → MVPClosed · **不跑 0c-2**

### 0c-2 Grid（fingerprint 過才跑）

```bash
python scripts/ft013_stf_counterfactual.py --cache-dir ../../../tick_cache --grid
```

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
