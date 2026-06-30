# Holdout A — 2025-05～2025-11

> Champion 候選：`early flow_turn → flow_turn+drive_low`，否則 `p0+drive_low`  
> _tune 區間 2026-01～05 未參與本 holdout_

## 結果

| 策略 | n | net_total | vs 封印 |
|------|---|-----------|---------|
| **p0 + sealed**（封印） | 31 | **+120.4** | baseline |
| p0 + drive_low（僅 P0 日） | 31 | **+197.8** | +77 |
| flow_turn + drive_low（全日） | 52 | -81.5 | — |
| **Champion 規則** | 52 | **-53.5** | **-173.9** |

## 月分解

| 月 | p0+sealed | champion |
|----|-----------|----------|
| 05 | -8 | -52 |
| 06 | +22 | **+98** |
| 07 | -11 | +13 |
| 08 | +57 | +41 |
| 09 | -36 | **-142** |
| 10 | +51 | +65 |
| 11 | +46 | **-77** |

## Holdout gate（自訂）

| 條件 | 結果 |
|------|------|
| 合計 net > 0 | **FAIL** (-53.5) |
| 無單月 < -150 | PASS |
| 優於封印 p0+sealed | **FAIL** (-174) |

## 解讀

1. **Champion 在 2026 H1 tune 上 +1408，在 2025 H2 holdout 上 -54** — 明顯過擬合 / regime 差異。
2. **9 月、11 月** flow_turn 日過多且虧損集中（最差單日 09-30 -84）。
3. **僅改 exit（p0+drive_low）** 在同期 **+198**，優於封印 — 進場不必全局 flow_turn。
4. **2026-06** holdout B 仍待資料；**現階段不建議封印 FT-018b champion**。

產物：`gudt_wash_probe_holdout_202505_202511.csv`
