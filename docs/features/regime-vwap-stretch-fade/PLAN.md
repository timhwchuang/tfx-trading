---
id: FT-012
slug: regime-vwap-stretch-fade
status: MVPClosed
opened: 2026-06-28
phases: [0]
blockers: []
---

# FT-012 — Regime VWAP Stretch Fade（PLAN）

> **Holdout**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **§2.1**

## Scope

- Phase 0 only：regime + 早盤窗 + stretch fade CF。
- 主判：**2025 train**；valid Q1 診斷；VSF 早盤無 regime 對照。

## Out of scope

- Plugin、UAT 切換、valid tune、holdout Q2。

## Phases

### Phase 0a — 文件 + CF 實作

- [x] `docs/features/regime-vwap-stretch-fade/{SPEC,PLAN}.md`
- [ ] `reporting/regime_vwap_stretch_fade_counterfactual.py`
- [ ] `scripts/ft012_regime_vwap_stretch_fade_counterfactual.py`
- [ ] `tests/reporting/test_regime_vwap_stretch_fade_counterfactual.py`

### Phase 0b — Code review

- [ ] Bugbot / 人類 review PASS（記於 `gate_report.md`）

### Phase 0c — Train CF

**結果（2026-06-28）**：**No-Go** — 2025 train 全 param net 負；regime 濾網未優於早盤無條件 VSF（見 `rvsf_vs_vsf_delta.json`）。

- [x] `workspaces/rvsf-baseline/reports/*.json`
- [x] `gate_report.md` + §Decision

### Phase 1+（train 過關後）

- [ ] `packages/strategies/regime-vwap-stretch-fade/` — **僅 train 過 + 人類 Go**

## Workspace

```
workspaces/rvsf-baseline/
  reports/
    counterfactual_rvsf_train.json
    counterfactual_rvsf_valid.json
    entry_funnel_rvsf.json
    rvsf_vs_vsf_delta.json
  gate_report.md
```

## Risks

| 風險 | 緩解 |
|------|------|
| Regime 定義 lookahead | 僅用已完成 bar + 嚴格 prior-day 歷史 |
| n < 30 | funnel 診斷；MVPClosed |
| 與 FT-006 同质 | `rvsf_vs_vsf_delta.json` |

## 參考

- [`vwap_stretch_fade_counterfactual.py`](../../../apps/trading-app/src/reporting/vwap_stretch_fade_counterfactual.py)
- [`ft011_scb_counterfactual.py`](../../../apps/trading-app/src/scripts/ft011_scb_counterfactual.py)
