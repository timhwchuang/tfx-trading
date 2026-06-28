---
id: FT-010
slug: vwap-trend-pullback
status: MVPClosed
opened: 2026-06-28
phases: [0, 1, 1a, 1b, 2, 3]
blockers: []
---

# FT-010 — VWAP Trend Pullback（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。  
> **排程**：FT-009 plugin / baseline 優先；FT-010 **僅文件就緒**，Phase 0 程式待 FT-009 測試收尾後開工。

## Phases

### Phase 0 — Counterfactual（01–03 主判 · long-only）

- [x] `docs/features/vwap-trend-pullback/{SPEC,PLAN}.md`
- [x] `reporting/vwap_trend_pullback_counterfactual.py`
- [x] `scripts/ft010_vtp_counterfactual.py`
- [x] `workspaces/vtp-baseline/reports/counterfactual_vtp_0103.json`
- [x] `workspaces/vtp-baseline/reports/counterfactual_vtp_valid.json`
- [x] `workspaces/vtp-baseline/reports/entry_funnel_vtp.json`
- [x] `workspaces/vtp-baseline/gate_report.md` — **01–03 未過**（n≪30）

**結果（2026-06-28）**：**No-Go** — 最佳 `rcy10` n=3、gross **+18.95**、net **+13.95**；G3 未過。04 valid **0 筆**。漏斗 stretch→buffer **27.8%**（未達 structural 門檻但樣本極少）。

**通過條件**（01–03 long only）：`gross_mean > 5`、`net_mean > 0`、`n ≥ 30`（見 SPEC §7）。

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft010_vtp_counterfactual.py \
  --code TMFR1 --cache-dir ../../../tick_cache \
  --train-from 2026-01-01 --train-to 2026-03-31 \
  --valid-from 2026-04-01 --valid-to 2026-04-30
```

**未過**：標 **MVPClosed at Phase 0**；不開 plugin、不跑 05 holdout。

### Phase 1 — Plugin + baseline（01–03 過關後）

- [ ] `packages/strategies/vwap-trend-pullback/`（複製 ORB / VSF 骨架）
- [ ] entry point `vwap_trend_pullback`
- [ ] `workspaces/vtp-baseline/config/config.yaml`
- [ ] `ft010_run_baseline.py`（或同等 baseline CLI）
- [ ] 04 valid baseline JSON

### Phase 1a — Mirror short（可選 · 封印至 long 過關）

- [ ] short leg counterfactual（**獨立** JSON / gate 表）
- [ ] long / short / combined 分欄報告；**combined 不作唯一 gate**

### Phase 1b — 執行對照（非 gate）

- [ ] Limit IOC vs market fill model
- [ ] UAT `compare_fill_audits`（模擬 API）

### Phase 2 — Holdout 05（04 valid 過 + 人類 Go 後解封）

- [ ] **一次** `baseline_holdout.json`（2026-05）
- [ ] 更新 SPEC §11 §Decision

### Phase 3 — 文件收尾

- [ ] `strategy_diagnosis.md` §10
- [ ] `docs/WeeklyStatus.md`
- [ ] 根 `CHANGELOG.md`（docs / strategy package）

## Workspace

```
workspaces/vtp-baseline/
  config/config.yaml          # Phase 1+
  reports/
    counterfactual_vtp_0103.json
    counterfactual_vtp_valid.json
    entry_funnel_vtp.json
    baseline_valid.json       # Phase 1
    baseline_holdout.json     # Phase 2（封印）
  gate_report.md
```

## 依賴與順序

| 前置 | 說明 |
|------|------|
| FT-009 Phase 1 | 目前進行中；FT-010 不搶 ORB plugin / 測試資源 |
| `tick_cache` TMFR1 01–05 | 與 FT-003 / FT-006 相同資料 SSOT |
| `orb_counterfactual` / `vwap_stretch_fade_counterfactual` | 複用 barrier sim、session_bucket、ATR 工具模式 |

## 參考

- SPEC：[`SPEC.md`](SPEC.md)
- ORB PLAN 範本：[`opening-range-breakout/PLAN.md`](../opening-range-breakout/PLAN.md)
- VSF counterfactual：[`apps/trading-app/src/reporting/vwap_stretch_fade_counterfactual.py`](../../../apps/trading-app/src/reporting/vwap_stretch_fade_counterfactual.py)
