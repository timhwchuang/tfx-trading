# FT-010b Gate Report — vtp-baseline（falsification）

> **Thesis G-b**：與 FT-010 相同，但 **移除**縮量 + 攻擊量門檻（FT-003 診斷：vol 非瓶頸）。
> **主判**：**01–03 合計** · 04 valid 參考。

## vs FT-010a（有量能濾網）

| 版本 | 01–03 總 n（rcy6+8+10） | 備註 |
|------|----------------------|------|
| FT-010a | 5 | 原 SPEC |
| **FT-010b** | **15** | 本報告 |

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **01–03** 2026-01-01～2026-03-31 | [`counterfactual_vtp_010b_0103.json`](reports/counterfactual_vtp_010b_0103.json) | **未過** |
| Valid 2026-04-01～2026-04-30 | [`counterfactual_vtp_010b_valid.json`](reports/counterfactual_vtp_010b_valid.json) | 未過（參考） |

## Funnel（01–03）

- stretch→buffer rate: 0.2778

## 01–03 — summary_by_param

| param | n | gross/趟 | net/趟 | QSL |
|---|---|----------|--------|-----|
| rcy10 | 8 | 24.44 | 19.44 | 0.375 |
| rcy6 | 3 | -30.29 | -35.29 | 0.6667 |
| rcy8 | 4 | -13.21 | -18.21 | 0.5 |

### Best passing（01–03）

**無通過組。**

## Valid 2026-04

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| rcy10 | 0 | None | None |
| rcy6 | 0 | None | None |
| rcy8 | 0 | None | None |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **仍 No-Go** — 砍 vol 仍無法 G1–G3；回踩 thesis 結構性死亡 |
| 備註 | 010b 為 pre-registered falsification，非 010a 事後 tune |
| UAT | **維持** `strategy-vwap-momentum` |
