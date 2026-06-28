# FT-017 Gate Report — cfa-baseline（Phase 0 · skew）

> **Thesis P-010**：Compression flow attack — 30m compress · quiet/attack tick flow · chase。
> **Entry**：tick chase on attack · **雙向** · friction **5**。
> **Exit**：`atr_barrier_900s` · G3S **n≥15**。

## Phase 0-design

| 項目 | 結果 |
|------|------|
| 資深 TXF P0 封印 | PASS（2026-06-28） |

## Phase 0b — Code review

| MUST | 結果 |
|------|------|
| MUST-1 compress+regime @ signal_1m | PASS（Bugbot 2026-06-28） |
| MUST-2 quiet/attack 60s · ratio/vol | PASS |
| MUST-3 tick chase · 結構 stop · min_stop | PASS |
| MUST-4 funnel 六階 | PASS |
| MUST-5 post_entry · skew 附錄 | PASS |

## Fingerprint (0c-1)

| 區間 | W30 stop-less med | n | barrier gross/趟 | 判定 |
|------|-------------------|---|----------------|------|
| Train 2025-01-01～2025-12-31 | None | 0 | None | **未過** |

### Funnel（絕對數）

- session_days=241 → compress_pass=0 → regime_pass=233 → quiet_pass=240 → attack_signal=236 → entry=0

### 驗屍（compress 錨點錯位 · 2026-06-28）

> **結論**：n=0 **不是** CF 漏跑或實作 slip；**MUST-1 的 30m compress 在 10:00–12:30 全年不可達**，與 flow attack 零重疊。禁止依本節回頭 tune FT-017 grid。

#### Funnel 為何「不像漏斗」

| 階段 | 計數語意 |
|------|----------|
| `quiet_pass` / `attack_signal` | 當日曾出現 quiet / ratio+vol（**獨立**於 compress） |
| `compress_pass` / `regime_pass` | **僅** attack 觸發當下、同一根 `signal_1m`（封印 A） |
| `entry` | compress ∧ regime ∧ stop 合格 |

故可見 `regime=233` 且 `compress=0`：**regime 常過、compress 從未過** — 非程式把順序寫反。

#### 全年 compress 審計（train 2025 · fingerprint 參數）

| 指標 | 值 |
|------|-----|
| 10:00–12:30 窗內 1m bar 數 | 36,391 |
| `compress_pass` bar 數 | **0** |
| 有任一 compress bar 的交易日 | **0 / 241** |
| 全年最小 30m `range_M` | **11.0 pt** |
| 最近 near-miss | 2025-07-16 11:41 · range_M=11 · 門檻≈4.5（ATR≈3.25） |

#### 設計錨點 vs 實作量級

| | 設計敘事（§E.1） | 實作 MUST-1 |
|--|------------------|-------------|
| 死魚振幅 | `compress_k=0.45 × ATR p50≈25.6` → **~12pt** | `range_M < 0.45 × max(ATR,10)` on **30×1m** maxHigh−minLow |
| baseline 對照 | **單根** 1m range p50≈9–25pt | 30m 區間典型 **50–110pt** |
| `range_M/ATR` 中位（10–12:30） | 隐含 ~0.45 | 實測 **5.32** |

**根因**：把 baseline「單根 1m range」與「30 根區間 range」混為同一錨點；`compress_k∈{0.35,0.45,0.55}` 離現實差 **~10×**，非 grid 微調可救。

#### quiet/attack 為何幾乎天天有

- `quiet`：`vol_1s p50≈4` → 240/241 日過
- `attack`：`vol_floor=max(30,p60)` 死魚日≈**30** 硬底 → 236/241 日 ratio+vol 過

前段極鬆、compress 極嚴 → **236 日有 flow 失衡、0 日同時 compress**。

#### compress_k 敏感度（診斷 only · 同 MUST-1 定義 · 前 50 日）

| compress_k | 過關 bar 數 |
|------------|-------------|
| 0.45 | 0 |
| 1.0 | 0 |
| 2.0 | 39 |
| 3.0 | 404 |
| 4.0 | 1459 |

#### 若復活故事（新 proposal · 非 FT-017）

1. **單根 1m compress** — 對齊 VOLATILITY_BASELINE 1m range p50
2. **compress @ quiet_end** — 非 attack 觸發當下（避免 attack 窗污染 30m range）
3. **維持 30m 但 compress_k≈3–5** — 敘事改為「盤整」非「死魚」

**Verdict**：`spec_anchor_mismatch` · `compress_gate_unreachable` · **不得** grid 救屍

## 進場後診斷（fingerprint · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | — | — |
| 180s MFE / MAE | — / — | — / — |
| W5m stop-less gross | — | — (net med —) |
| W15m stop-less gross | — | — (net med —) |
| W30m stop-less gross | — | — (net med —) |

**Verdict**: `insufficient_n`

- n < 5

## Skew 附錄（fingerprint · 診斷）

- payoff_ratio=None · tail_count=None
- net_mean@friction7=None · top3_share=None
- slippage extra mean net: {'extra_0': None, 'extra_1': None, 'extra_2': None}

> execution_margin_thin：tick chase 薄流動性 · Pilot IOC ±3 未在 0c 模擬。

## Grid (0c-2)

*未執行 — 0c-1 結果見 §Decision*

## Valid 2026 Q1（參考 · skew 硬擋）

- n=0 · gross/趟=None · net/趟=None

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `cfa_fingerprint_fail` |
| outcome | `cfa_fingerprint_fail` |
| thesis_class | **skew** |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |
