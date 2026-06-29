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
| MUST-1 compress+regime @ signal_1m | pending |
| MUST-2 quiet/attack 60s · ratio/vol | pending |
| MUST-3 tick chase · 結構 stop · min_stop | pending |
| MUST-4 funnel 六階 | pending |
| MUST-5 post_entry · skew 附錄 | pending |

## Fingerprint (0c-1)

| 區間 | W30 stop-less med | n | barrier gross/趟 | 判定 |
|------|-------------------|---|----------------|------|
| Train 2025-01-01～2025-12-31 | None | 0 | None | **未過** |

### Funnel（絕對數）

- session_days=241 → compress_pass=0 → regime_pass=241 → quiet_pass=241 → attack_signal=241 → entry=0

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
| 決策 | **MVPClosed**（已跑 CF · 歷史事實） |
| outcome | **`spec_anchor_mismatch`**（canonical · 0-design） |
| mislabel | `cfa_fingerprint_fail` — 非 fingerprint 失敗；見 Playbook §3.1a |
| thesis_class | **skew** |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |

## §驗屍（compress 錨點 · spec_anchor_mismatch）

> SSOT：[`GATE_COVERAGE_PREFLIGHT.md`](../../docs/features/ai-backtest-tuning/GATE_COVERAGE_PREFLIGHT.md) 附錄 A · [`CORPSE_ATLAS.md`](../../CORPSE_ATLAS.md) §FT-017

| 項目 | 值 |
|------|-----|
| 子類備註 | `compress_gate_unreachable` |
| 10:00–12:30 compress bars | **0 / 36,391** |
| range_M/ATR p50 | **5.32** vs 設計隱含 **~0.45** |
| 單根 1m range p50 | **9.0 pt**（錯誤敘事錨點） |
| `compress_k` 0.35–0.55 | **0 bar** 全年 |

**教訓**：應在 Preflight 擋下、退回 SPEC/PLAN — **不應**進 0a／標 fingerprint fail。
