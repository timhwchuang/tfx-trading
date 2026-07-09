# FT-010 Gate Report — vtp-baseline（Phase 0）

> **Thesis G**：VWAP Trend Pullback — Phase 0 **long-only**。
> **主判**：**01–03 合計** · 04 valid 參考。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **01–03** 2026-01-01～2026-03-31 | [`counterfactual_vtp_0103.json`](reports/counterfactual_vtp_0103.json) | **未過** |
| Valid 2026-04-01～2026-04-30 | [`counterfactual_vtp_valid.json`](reports/counterfactual_vtp_valid.json) | 未過（參考） |

## Funnel（01–03）

- trading_days: 54
- days_with_stretch_env: 54
- days_with_buffer_touch: 15
- stretch→buffer rate: 0.2778
- structural_band_unreachable: False

## 01–03 主判 — summary_by_param

| param | n | gross/趟 | net/趟 | QSL |
|---|---|----------|--------|-----|
| rcy10 | 3 | 18.95 | 13.95 | 0.0 |
| rcy6 | 1 | -40.86 | -45.86 | 0.0 |
| rcy8 | 1 | -40.86 | -45.86 | 0.0 |

### Best passing（01–03）

**無通過組。**

## Valid 2026-04（參考 only）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| rcy10 | 0 | None | None |
| rcy6 | 0 | None | None |
| rcy8 | 0 | None | None |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **No-Go at Phase 0** (`thesis_g_vtp_no_go`) |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |
