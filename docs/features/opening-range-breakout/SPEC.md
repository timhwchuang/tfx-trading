---
id: FT-009
slug: opening-range-breakout
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/opening-range-breakout/SPEC.md
audit_schema_version: 1
---

# FT-009 — Opening Range Breakout（Thesis F）

> **SPEC** = 開盤區間突破、低頻順勢 thesis。**拋開** vol spike / VWAP / 全時段 rolling breakout。Pre-registered 參數；**01–04 主判**。

## 1. Summary

**問題**：FT-004～008 在高頻「事件後行為」上反覆接近 gate 但跨月失敗；FT-008 edge 在 close_1h，open 桶偏弱 — 需用 **session-anchored** 假說反證開盤是否可交易。

**目標**：08:45 起 **R 分鐘** 定義 opening range；區間結束後 **first break only** 順勢進場；出場 ATR-scaled。

**使用者**：`workspaces/orb-baseline` Phase 0；UAT 不切換直至 01–04 過關 + 人類 Go。

## 2. 現況 vs 目標

| 面向 | FT-008 short breakout | **FT-009 ORB** |
|------|----------------------|----------------|
| 區間 | rolling N-bar 任意時段 | **固定開盤 R 分鐘** |
| 頻率 | 高（百筆/月） | **低（≤1 筆/日）** |
| 開盤 | skip 10m | **專做開盤** |
| Gate 主判 | 曾以 4 月為主 | **01–04 合計** |

## 3. 進場契約（MUST — Phase 0 CF，pre-registered）

1. **區間**：`range_minutes ∈ {15, 30}`（08:45 起算，不含區間外 bar）。
2. **高低**：區間內 1m bar High/Low。
3. **濾網**：`range_width ≥ min_range_atr_k × ATR`（預設 0.5）；否則 skip 當日。
4. **突破**：區間結束後第一根 **close** 突破 `range_high/low ± buffer_atr_k × ATR`；`buffer ∈ {0, 0.15}`。
5. **頻率**：**first break only** — 每日最多 1 筆（多/空先觸發者）。
6. **出場**：`hard_stop_atr_k=0.75`、`tp_atr_k=2.0`、`max_hold_sec=180`。

**禁止**：額外 sweep、子集切片、4 月單獨 tune 作過關依據。

## 4. Go / No-Go Gates

| Gate | 條件 |
|------|------|
| **G1** | 01–04 gross/趟 **> 5** |
| **G2** | 01–04 net/趟 **> 0** |
| **G3** | n **≥ 30** |
| **參考** | valid 2026-04 僅對照，不作主判 |

產物：[`workspaces/orb-baseline/gate_report.md`](../../../workspaces/orb-baseline/gate_report.md)。

## 5. Definition of Done

- [x] `ft009_orb_counterfactual.py` + JSON + gate_report
- [x] Phase 0 決策 — **01–04 通過**（rm30_bk0p15）
- [x] plugin + baseline（01–04：73 趟 net +1.29）
- [x] holdout 2026-05 — **未過**（凍結 rm30_bk0p15 net −8.64；v1 `holdout_fail_structural`）
- [ ] holdout v2 05+06 — **待 06 tick**（[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)）

## 8. §Decision — MVPClosed（2026-06-28）

| 欄位 | 值 |
|------|-----|
| Phase 0 | **通過** — 01–04 `rm30_bk0p15` n=73 gross **+7.93** net **+2.93** |
| Phase 1 plugin | **完成** — 73/73 成交；01–04 plugin net **+1.29** |
| Holdout 05 v1 | **未過** — CF/plugin 雙雙 net 負（凍結 param）；`holdout_fail_structural` |
| Holdout v2 05+06 | **未跑**（06 待 backfill） |
| 決策 | **MVPClosed**（`thesis_f_orb_holdout_no_go`）— 不進 UAT |
| UAT/Live | **維持** `strategy-vwap-momentum` |

產物 SSOT：[`workspaces/orb-baseline/gate_report.md`](../../../workspaces/orb-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §8
- Holdout v2：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)
- FT-008：[`short-breakout/SPEC.md`](../short-breakout/SPEC.md) §8
