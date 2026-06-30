# Feb 2026 Wash Probe v2 — 修正 wash 時序後

**改動**：從 `BREAK_START` 起追 `drive_high` 下洗盤（不綁 first_break）；新增 `drive_low_struct` 停損；`sell_ratio` / `vol_shrink` 欄位。

## 全月 2026-02（6 個 flow_turn 日）

| 策略 | n | net_total |
|------|---|-----------|
| p0 + sealed | 5 | **-170.8** |
| flow_turn + wash_struct | 6 | **+20.8** |
| flow_turn + drive_low_struct | 6 | **+248.8** |
| flow_turn + momentum_tail | 6 | **+182.5** |
| reclaim_br + momentum_tail_trail | 4 | **+260.5** |

## Panel 5 日（02-09/10/11/24/25）

| 日 | p0+sealed | flow_turn+wash_struct | flow_turn 進場 | ΔBR |
|----|-----------|----------------------|----------------|-----|
| 02-09 | -53 | **+49** | 09:45 @32573 | 0.133 |
| 02-10 | -50 | **+46** | 09:45 @33075 | 0.167 |
| 02-11 | -5 | **+25** | 09:56 @33510 | 0.182 |
| 02-24 | -58 | **+3** | 09:50 @34558 | 0.125 |
| 02-25 | -5 | **+74** | 10:01 @35343 | 0.145 |

Panel 合計 flow_turn+wash_struct ≈ **+197** vs p0+sealed **-171**

## 結論

1. **wash 時序 bug 是主因** — 修正後 `flow_turn` 在破 dh 前即觸發（02-09/10 皆 09:45）。
2. **wash_struct 翻正**（全月 +21；panel +197），但 **drive_low 停損更穩**（全月 +249）。
3. **vol_shrink** 初版在 flow_turn 進場點皆 False — 需改為「洗盤段落內」量縮偵測（非進場當下 90s）。
4. **sell_ratio** 在 flow_turn 進場約 0.33–0.62（賣壓非極端）— 可再當輔助篩選。

產物：`gudt_wash_probe_202602_v2.csv`、`gudt_wash_probe_feb_panel_v2.md`
