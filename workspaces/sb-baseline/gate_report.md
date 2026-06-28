# FT-008 Gate Report — sb-baseline（Phase 0）

> **狀態：子集通過 / 全 cohort No-Go** — 見 [`SPEC §8`](../../docs/features/short-breakout/SPEC.md)。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **Valid 2026-04** | [`counterfactual_short_breakout.json`](reports/counterfactual_short_breakout.json) | **通過**（close_1h 子集） |
| **01–04 合計** | [`counterfactual_short_breakout_0104.json`](reports/counterfactual_short_breakout_0104.json) | **未過** |

## Valid 2026-04 — Phase 0 預檢

| 通過 | True |
| gross_mean 門檻 | > 5.0 |
| net_mean 門檻 | > 0.0 |
| min_n | 30 |

**FT-004 對照**（armed 全進 valid）：gross ~ **1.89**/趟（G1 未過）→ FT-008 **close_1h 子集**優於 FT-004 全 cohort。

### Best passing（param × bucket）

- `lb10_bk0.1` × **close_1h**
- n=**67** gross_mean=**7.24** net_mean=**2.24**

### 全 param 合計（atr_barrier_180s）— 皆未過 G2

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb5_bk0 | 574 | 1.06 | **−3.94** |
| lb10_bk0.1 | 433 | 0.77 | **−4.23** |
| lb15_bk0.1 | 362 | 0.47 | **−4.53** |

**解讀**：edge 集中在 **收盤前 1h**；mid / open_30m 拖累全 cohort。

---

## 01–04 合計 — Phase 0 預檢

| 通過 | **False** |
| 最佳 close_1h | lb15_bk0.1：n=198 gross **4.40** net **−0.60**（G1 未過） |

### 全 param 合計（atr_barrier_180s）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb10_bk0 | 1736 | 1.35 | **−3.65** |
| lb10_bk0.1 | 1563 | 1.38 | **−3.62** |
| lb5_bk0 | 2136 | 1.25 | **−3.75** |

**解讀**：與 FT-006 holdout 教訓類似 — **valid 月子集可過、跨月合計稀釋**；不宜直接開全時段 plugin。

---

## 對照

| Thesis | valid 最佳 | 01–04 |
|--------|-----------|-------|
| FT-004 armed 全進 | gross +1.89 | — |
| FT-006 VWAP fade | gross +5.43（全月） | holdout 掛 |
| **FT-008 breakout** | close_1h gross **+7.24** | close_1h gross **+4.40**（G1 未過） |

---

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **No-Go 全時段 plugin**；**保留** close_1h + lb10 假說作 Phase 0 v2（`close_1h_only`） |
| 理由 | 01–04 無任一組 gross>5 & net>0；April 子集通過但 overfit 風險 |
| Plugin | **不開**（待 v2 或人類核准窄 cohort pilot） |
| UAT | **維持** `strategy-vwap-momentum` |
| v2 | 見 [`gate_report_v2.md`](gate_report_v2.md) — **Hold**（01–04 未過） |
| 日期 | 2026-06-28 |
