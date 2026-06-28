# Corpse Atlas — 驗屍索引（post-entry 診斷）

> **用途**：對 MVPClosed thesis **一次性**補跑 `post_entry_diagnosis`（W5/W15/W30 + MFE/MAE）。  
> **不是**重開 grid、不是救屍、**不得**依結果 tune。  
> **v2.2 skew 契約不推翻本表** — 見 Holdout §11。
> 彙總 JSON：[`CORPSE_ATLAS_results.json`](CORPSE_ATLAS_results.json)  
> 腳本：`python scripts/run_corpse_atlas_batch.py` · `retrofit_post_entry_diagnosis.py`

---

## §結果彙總（2026-06-28）

| FT | 區間 | champion | n | barrier med | W5 | W30 | MFE/MAE med | verdict |
|----|------|----------|---|-------------|-----|-----|-------------|---------|
| **006** | 2025 train k=2.0 | 2.0 | 268 | −18.75 | **+5.0** | −1.5 | 18/19 | direction_failed |
| **006** | 2026 Q1 valid | 2.0 | 298 | −18.75 | −2.0 | −9.5 | 22/19 | direction_failed |
| **006** | legacy 2026-04 | 2.0 | 147 | −18.75 | −3.0 | +10.0 | 24/19 | exit_kills_edge |
| **012** | 2025 train k2_p30 | k2_p30 | 133 | −7.31 | +2.0 | **+4.0** | 11/8 | direction_ok_margin_thin |
| **009** | 01–04 rm30_bk0p15 | — | 73 | −6.0 | +2.0 | +5.0 | 36/19 | direction_ok_margin_thin |
| **009** | valid | — | 19 | −25.88 | −22.0 | +5.0 | 33/28 | direction_ok_margin_thin |
| **009** | holdout 05 | — | 19 | −33.34 | −17.0 | +56.0 | 25/38 | exit_kills_edge |
| **011** | 2025 train rm30 | rm30 | 46 | −24.65 | −2.0 | −3.0 | 30/25.5 | direction_failed |
| **015** | 2025 train fp | sl3 | 211 | -3.0 | 1.0 | **-0.0** | 17/18 | direction_weak |
| **014** | 2025 train fp | hm10 | 7 | 50.0 | 36.0 | **+38.0** | 50/15 | direction_ok_margin_thin |
| **013** | 2025 train fp | ap10_sm3 | 67 | −4.0 | −5.0 | **−10.0** | 7/15 | direction_failed |
| **013** | 2026 Q1 valid fp | ap10_sm3 | 26 | +14.5 | +7.0 | +7.5 | 36/28 | direction_ok_margin_thin |
| **008** | valid lb15 | — | 72 | −1.0 | +4.5 | −5.0 | 17/14 | direction_failed |
| **007** | flow flip pilot | all | 108 | +2.5 | +1.5 | +1.0 | 8/7 | direction_weak |
| **010** | 01–03 | — | 低 n | — | — | — | — | MVPClosed |

**MFE 深度分析（FT-006 k=2.0 train）**：[`mfe_context_k2_train2025.json`](vsf-baseline/reports/mfe_context_k2_train2025.json)

---

## 快 vs 慢

| 類型 | 條件 | 耗時 |
|------|------|------|
| **快** | JSON 含 `entries` | ~1–3 分鐘/案 |
| **慢** | 重跑 CF builder | ~5–12 分鐘/全年 |

---

## 解讀規則

1. verdict **不推翻** MVPClosed  
2. W30 net median ≤ 0 → 無可交易 edge（扣 5 點摩擦）  
3. 詳見 Playbook post_entry 附錄規則
