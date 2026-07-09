---
id: FT-011
slug: session-confluence-breakout
status: MVPClosed
opened: 2026-06-28
phases: [0, 1, 1b, 2, 3]
blockers: []
---

# FT-011 — Session Confluence Breakout（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。  
> **Holdout**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **§2.1**（2025 train · 2026 Q1 valid · 2026 Q2 holdout）。

## Scope

- Phase 0 counterfactual：時段選擇性 OR 突破 + VWAP 趨勢 + 量能/波動共振（**long-only**）。
- 主判：**2025 全年 train**；valid Q1 對照；holdout Q2 封印。
- **ORB 對照產物**（同 rm20/rm30、bk=0）：量化 confluence 增量。

## Out of scope

- Phase 0：Limit 掛單、前日高點突破、雙向 gate、結構高點 TP cap。
- UAT 策略切換（維持 `strategy-vwap-momentum`）。

## Dependencies & blockers

| 項目 | 狀態 |
|------|------|
| `tick_cache` TMFR1 2025 + 2026 Q1 | ✅（2025 247 日） |
| Holdout v2.1 文件 | ✅ |
| `orb_counterfactual.py` | ✅ 複用 OR 計算 + barrier exit |
| 2026-06 tick（holdout 完整） | 🔲 待落地 → `holdout_partial` |

## Phases

### Phase 0 — 文件 + Counterfactual

**文件**
- [x] `docs/features/session-confluence-breakout/{SPEC,PLAN}.md`
- [x] `docs/features/README.md` board
- [x] `DOC_MAP.md` + `CHANGELOG.md`

**程式**
- [x] `reporting/scb_counterfactual.py` — 複用 [`orb_counterfactual.py`](../../../apps/trading-app/src/reporting/orb_counterfactual.py) OR 計算、`simulate_atr_barrier_exit`、session VWAP 累積
- [x] `scripts/ft011_scb_counterfactual.py`
- [x] `workspaces/scb-baseline/reports/counterfactual_scb_train.json`
- [x] `workspaces/scb-baseline/reports/counterfactual_scb_valid.json`
- [x] `workspaces/scb-baseline/reports/entry_funnel_scb.json`
- [x] `workspaces/scb-baseline/reports/scb_vs_orb_delta.json`
- [x] `workspaces/scb-baseline/gate_report.md`（v2.1 模板）

**結果（2026-06-28）**：**No-Go** — 2025 train 全 param net 負 + §3.1 disqualify；valid Q1 rm30 表面過關 → overfit_suspect；ORB delta 顯示 confluence 減損虧損但未轉正。

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft011_scb_counterfactual.py \
  --code TMFR1 --cache-dir ../../../tick_cache \
  --train-from 2025-01-01 --train-to 2025-12-31 \
  --valid-from 2026-01-01 --valid-to 2026-03-31
```

**未過**：標 **MVPClosed at Phase 0**；不開 plugin、不解封 holdout。

### Phase 1 — Plugin + baseline（train 過關後）

- [ ] `packages/strategies/session-confluence-breakout/`（ORB package 骨架）
- [ ] entry point `session_confluence_breakout`
- [ ] `workspaces/scb-baseline/config/config.yaml`
- [ ] `ft011_run_baseline.py`（或同等 baseline CLI）
- [ ] valid Q1 baseline JSON

### Phase 1b — 執行對照（非 gate）

- [ ] Limit @ `range_high + offset` vs market @ close
- [ ] 結構高點 TP cap 子版本（若需）

### Phase 2 — Holdout（valid 過 + 人類 Go）

- [ ] **一次** `baseline_holdout.json`（2026-04-01 … 2026-06-30）
- [ ] 06 未落地時標 `holdout_partial`；06 補齊後合併重判
- [ ] 更新 SPEC §10 §Decision

### Phase 3 — 文件收尾

- [ ] `strategy_diagnosis.md` 新 §
- [ ] `docs/WeeklyStatus.md`（若適用）
- [ ] 根 `CHANGELOG.md`（strategy package 條目）

## Workspace

```
workspaces/scb-baseline/
  config/config.yaml          # Phase 1+
  reports/
    counterfactual_scb_train.json
    counterfactual_scb_valid.json
    entry_funnel_scb.json
    scb_vs_orb_delta.json
    baseline_valid.json       # Phase 1
    baseline_holdout.json     # Phase 2（封印）
  gate_report.md
```

## Acceptance（關閉整張 ft）

- [ ] SPEC §9 Definition of Done 全勾
- [ ] Holdout H1–H5 通過 + 人類書面 Go
- [ ] `bash scripts/run-all-tests.sh` 全綠（若涉及程式）

## Risks

| 風險 | 緩解 |
|------|------|
| Confluence AND 導致 n<30 | funnel + `scb_vs_orb_delta.json` 量化濾網成本 |
| 與 ORB 同质 | ORB delta 必產；同窗 bk=0 對照 |
| 低頻 holdout n | v2.1 三月合併；低頻 H3 n≥20 |
| 2025 vs 2026 regime | valid Q1 `overfit_suspect` 紅旗 |
| 尾盤 bucket 樣本少 | G5-bucket 診斷；必要時 Phase 1b 收斂尾盤窗 |

## Land checklist（併入 app SPEC 前必勾）

- [ ] 穩定契約已寫入 `packages/strategies/session-confluence-breakout/SPEC.md`
- [ ] `CHANGELOG.md` 已記行為/API 變更
- [ ] `docs/features/README.md` Status → **Landed** 或 **MVPClosed**
- [ ] SPEC/PLAN frontmatter `status` 更新
- [ ] 本 PLAN 所有 Phase checkbox 已勾

## 參考

- SPEC：[`SPEC.md`](SPEC.md)
- Holdout v2.1：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)
- ORB PLAN：[`opening-range-breakout/PLAN.md`](../opening-range-breakout/PLAN.md)
- VTP counterfactual：[`vwap_trend_pullback_counterfactual.py`](../../../apps/trading-app/src/reporting/vwap_trend_pullback_counterfactual.py)
