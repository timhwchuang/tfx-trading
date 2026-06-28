---
id: FT-008
slug: short-breakout
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/short-breakout/SPEC.md
audit_schema_version: 1
---

# FT-008 — Short Breakout（Thesis E）

> **SPEC** = 1m 結構化突破順勢 thesis。**完全拋開** VWAP 回踩、fade、flow flip。v1 hybrid、FT-006/007 **凍結**為研究參考。

## 1. Summary

**問題**：FT-004/005 顯示 1s armed 全進與 timeout 延遲進場均 No-Go；但 diagnosis §6.1 **timeout 子集** W180 **+35**、MFE 69 — 順勢延續 edge 存在於「未回踩」脈衝，被 v1 進場結構排除。

**目標**：以 **1m K 棒** 前 N 根高/低突破 + **成交量放大** + **ATR/range 確認** 定義順勢進場；出場 **ATR-scaled**（沿用 FT-004）並附固定點數對照。

**使用者**：回測 / `workspaces/sb-baseline`；UAT 切換須 G2 + 人類 Go + holdout。

## 2. 現況 vs 目標

| 面向 | FT-004 / FT-005 / FT-007 | **FT-008** |
|------|--------------------------|------------|
| 信號 | 1s spike armed / timeout / flow flip | **1m 高/低突破** |
| 方向 | 順勢全進 / 延遲 / 逆勢 fade | **順勢**（突破方向） |
| 確認 | vol_1s 極右尾 | **bar vol 分位 + range×ATR** |
| 時段 | 全時段或子集實驗 | **略過開盤前 10 分** |
| 出場 | ATR 或固定點 | ATR 主、固定點對照 |

## 3. 進場契約（MUST — Phase 0 CF）

1. **K 棒**：1m archived kbars（`{code}_kbars_{date}.csv`）；ATR = SMA(TR, 20)。
2. **突破**：bar close 突破前 `lookback_bars` 根（不含當根）最高/最低，且超出 `breakout_atr_k × ATR`（初探 0.0 / 0.1）。
3. **方向**：向上突破 → **Long**；向下 → **Short**。
4. **量能**：當根 bar volume ≥ 當日 session `vol_pct` 分位（預設 70）。
5. **ATR 確認**：當根 range ≥ `min_range_atr_k × ATR`（預設 0.5）。
6. **時段**：`ts ≥ session_open + skip_open_min`（預設 10 分，即 08:55 起）；`session_bucket` 分組同 FT-006。
7. **去抖**：`cooldown_sec`（預設 120）內不重複進場。
8. **Audit（Phase 2+）**：`SIGNAL_AUDIT reason=short_breakout`；**無** `momentum_armed`。

## 4. 出場契約（MUST — 繼承 FT-004）

| 參數 | 語意 | 基準初值 |
|------|------|----------|
| `hard_stop_atr_k` | 硬停 | 0.75 |
| `tp_atr_k` | 止盈（barrier sim） | 2.0 |
| `max_hold_sec` | 時間停 | 180 |

**研究對照**：固定 `sl_points=8` / `tp_points=12` / `max_hold_sec=120`（`simulate_scalp_exit`）。

## 5. Go / No-Go Gates

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | gross expectancy/趟 **> 5** | 不 sweep |
| **G2** | net **> 0**（摩擦 5 點/趟） | 僅診斷 |
| **G3** | trade_count **< 100**/月（01–04 合計 **< 400**） | 檢討過濾 |
| **G4** | QSL **< 25%** | 調 `hard_stop_atr_k` |
| **G5** | 01–04 無單月 net < −2/趟 | Phase 2 才評 |

**Phase 0 預檢**：存在至少一組（`lookback_bars` × `session_bucket`）`gross_mean > 5`、`net_mean > 0`、`n ≥ 30` → 才開 plugin；否則 **MVPClosed at Phase 0**。

**對照**：Phase 0 報告 **MUST** 引用 FT-004 valid gross（~+1.89/趟）作為順勢基準線。

產物：[`workspaces/sb-baseline/gate_report.md`](../../../workspaces/sb-baseline/gate_report.md)。

## 6. Definition of Done

- [x] `ft008_short_breakout_counterfactual.py` + JSON
- [x] Phase 0 決策（子集通過 / 01–04 未過）
- [ ] `strategy-short-breakout` plugin（**暫緩** — 待 close_1h v2 或人類核准）
- [ ] `sb-baseline` baseline + holdout
- [x] 本 SPEC + PLAN

## 8. §Decision — Phase 0 子集通過、01–04 No-Go（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 結論 | **Thesis E 全 cohort No-Go**；**close_1h 子集** valid 通過 Phase 0 |
| Valid 2026-04 最佳 | `lb10_bk0.1` × close_1h：n=67 gross **+7.24**、net **+2.24** |
| 01–04 最佳 close_1h | `lb15_bk0.1`：n=198 gross **+4.40**、net **−0.60**（G1 未過） |
| vs FT-004 | close_1h 子集 **優於** armed 全進（+1.89） |
| Plugin | **不開** — overfit 風險同 FT-006；v2 close_1h_only 見下 |
| UAT/Live | **維持** `strategy-vwap-momentum` |

### v2 close_1h_only（2026-06-28）

| 區間 | 結果 |
|------|------|
| Valid 2026-04 | **通過** — `lb10_bk0.1` n=67 gross **+7.24** net **+2.24** |
| 01–04 | **未過** — best `lb10_bk0.1` n=198 gross **+4.40** net **−0.60** |
| 決策 | **Hold** — 不開 plugin；見 [`gate_report_v2.md`](../../../workspaces/sb-baseline/gate_report_v2.md) |

產物 SSOT：[`workspaces/sb-baseline/gate_report.md`](../../../workspaces/sb-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6.1、§7
- FT-004 基準：[`mc-baseline/gate_report.md`](../../../workspaces/mc-baseline/gate_report.md)
- FT-004 出場：[`momentum-continuation/SPEC.md`](../momentum-continuation/SPEC.md) §4
