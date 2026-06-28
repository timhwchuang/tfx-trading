---
id: FT-012
slug: regime-vwap-stretch-fade
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: —
stable_contract: packages/strategies/regime-vwap-stretch-fade/SPEC.md
audit_schema_version: 1
---

# FT-012 — Regime VWAP Stretch Fade（Thesis I · P-001）

> **SPEC** = 低波動 regime 條件下的 VWAP stretch fade。**主判**：Holdout v2.1 **2025 train**。

## 1. Summary

**問題**：FT-006 無條件 VWAP fade — legacy valid 過、holdout 與 **v2.1 train 2025 未過**；edge 疑似僅存在特定 regime / 時段。

**目標**：僅在 **早盤 09:00–10:30**、**低波動 regime**（歷史分位）、且 **|z| ≥ stretch_k** 時反向 fade；出場 ATR-scaled（FT-006 語意）。

**不是 FT-006 因為**：三層門檻（時段 + regime + stretch）；非全 session 無條件 fade。

**不是 P-002 因為**：非 midday 假突破；核心仍是 VWAP z-score fade。

**使用者**：`workspaces/rvsf-baseline` Phase 0 CF only（train 未過不開 plugin）。

## 2. 進場契約（MUST — pre-registered）

| ID | 規則 |
|----|------|
| W1 | `09:00 ≤ t < 10:30`（交易所時間） |
| R1 | `rv_recent` = 過去 **30** 根已完成 1m bar 的 log return **母體**標準差 |
| R2 | `regime_pct` = 在**過去 20 個交易日**、**相同 clock time** 的 `rv_recent` 樣本中，今日值的百分位（%）；樣本 < **5** → 不進場 |
| R3 | `regime_pct ≤ vol_pct_max` |
| Z1 | `z = (price − vwap_5m) / ATR_raw`；**無** 25pt ATR floor |
| Z2 | `|z| ≥ stretch_k`；`z>0` → Short；`z<0` → Long |
| D1 | `reset_z=0.5`、`cooldown_sec=60`（凍結） |

## 3. 出場契約

| 參數 | 值 |
|------|-----|
| `hard_stop_atr_k` | 0.75 |
| `tp_atr_k` | 2.0 |
| `max_hold_sec` | 180（barrier sim） |
| 摩擦 | 5 點/趟 |

## 4. Phase 0 Grid（僅 2025 train）

| 參數 | 值 |
|------|-----|
| `stretch_k` | 2.0, 2.5, 3.0 |
| `vol_pct_max` | 25, 30, 35 |

**封印**：valid 2026 Q1、holdout Q2 — 不得依結果改 grid。

## 5. Gate（v2.1 train）

見 [`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §3、§3.1。冠軍：`net/趟` 最高（平手 → n 大）。

## 6. 產物

- `counterfactual_rvsf_train.json` / `counterfactual_rvsf_valid.json`
- `entry_funnel_rvsf.json`
- `rvsf_vs_vsf_delta.json`（早盤窗 + k=2.0、**無 regime** 對照）
- `gate_report.md`

## 7. Funnel

`days` → `in_morning_window` → `regime_ok` → `stretch_ok` → `entry`

## 8. §Decision — MVPClosed at Phase 0（2026-06-28）

| 欄位 | 值 |
|------|-----|
| Train 2025 | **未過** — 全 9 組 net 負；最佳 k2_p30 n=133 gross **+0.75** net **−4.25**；§3.1 disqualify（median **−7.31**） |
| Valid Q1 | 全 param net 負（診斷） |
| VSF delta | 早盤 k=2.0 無 regime n=650 net **−2955**；regime 濾網 **未**轉正 |
| 標籤 | `thesis_i_rvsf_no_go` |
| 決策 | **MVPClosed** — 不開 plugin |
| Code review | PASS 2026-06-28（Bugbot RV lookahead 修正後 train） |

產物：[`gate_report.md`](../../../workspaces/rvsf-baseline/gate_report.md)

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- FT-006：[`vwap-stretch-fade/SPEC.md`](../vwap-stretch-fade/SPEC.md) §8
- Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)
- Queue：[`THESIS_QUEUE.md`](../../../workspaces/THESIS_QUEUE.md) P-001
