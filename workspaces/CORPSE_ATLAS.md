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
| **016** | 2025 train fp | gk1_rt0p4 | 79 | −1.0 | 3.0 | **+13.0** | 25/21 | exit_kills_edge |
| **016** | 2026 Q1 valid fp | gk1_rt0p4 | 15 | — | — | — | — | holdout_blocked |
| **014** | 2025 train fp | hm10 | 7 | 50.0 | 36.0 | **+38.0** | 50/15 | direction_ok_margin_thin |
| **013** | 2025 train fp | ap10_sm3 | 67 | −4.0 | −5.0 | **−10.0** | 7/15 | direction_failed |
| **013** | 2026 Q1 valid fp | ap10_sm3 | 26 | +14.5 | +7.0 | +7.5 | 36/28 | direction_ok_margin_thin |
| **008** | valid lb15 | — | 72 | −1.0 | +4.5 | −5.0 | 17/14 | direction_failed |
| **007** | flow flip pilot | all | 108 | +2.5 | +1.5 | +1.0 | 8/7 | direction_weak |
| **017** | 2025 train fp | ck0p45 | **0** | — | — | — | — | **spec_anchor_mismatch** |
| **010** | 01–03 | — | 低 n | — | — | — | — | MVPClosed |

**MFE 深度分析（FT-006 k=2.0 train）**：[`mfe_context_k2_train2025.json`](vsf-baseline/reports/mfe_context_k2_train2025.json)

---

## 快 vs 慢

| 類型 | 條件 | 耗時 |
|------|------|------|
| **快** | JSON 含 `entries` | ~1–3 分鐘/案 |
| **慢** | 重跑 CF builder | ~5–12 分鐘/全年 |

---

## §Fingerprint 審計（W 窗 vs hold · v1.5）

> **用途**：對照 Playbook §3.1b — 新 FT **MUST** pre-register `fingerprint_window_sec`；**禁止**依屍体 post_entry 回頭改窗。

| FT | hold `max_hold_sec` | gate fingerprint 窗 | W900 med | Long W900 | trail exit? | barrier med | legacy W1800 med | MFE med | `exit_gap`≈ | 設計含意 |
|----|---------------------|---------------------|----------|-----------|-------------|-------------|------------------|---------|-------------|----------|
| **016** GDC | 900 | W1800（legacy W30m） | — | — | 否 · barrier | −1.0 | **+13** | 25 | **~26** | **exit_kills_edge** → FT-018 |
| **015** FRP | 900 | W1800（legacy W30m） | **+1.0** | **+3.0** | 否 · barrier | −3.0 | **−0.0** | 17 | **~20** | **exit_kills_edge**（非 direction_failed）→ FT-019 锚点 |
| **013** STF | 900 | W1800 | — | — | 否 | −4.0 | −10.0 | 7 | ~11 | direction_failed |
| **014** MVHP | 900 | W1800 | — | — | 否 | 50.0 | +38 | 50 | ~0 | funnel 過稀 · n=7 |
| **012** RVSF | — | W1800 | — | — | 否 | −7.3 | +4 | 11 | ~18 | fade 族 · margin thin |
| **006** VSF | — | W1800 | — | — | 否 | −18.8 | −1.5 | 18 | ~37 | direction_failed |

**FT-018 / FT-019 對齊**：`fingerprint_window_sec=900`（**W900**）· 與 hold 一致 · **禁止** legacy W1800 作新 FT gate。

---

## §FT-017 驗屍（funnel · compress 錨點 · 2026-06-28）

> **n=0** — 無 post_entry 列；死因在 **MUST-1 不可達**，非 chase 方向未測。  
> 詳述：[`cfa-baseline/gate_report.md`](cfa-baseline/gate_report.md) §驗屍。

| 項目 | 值 |
|------|-----|
| outcome | **`spec_anchor_mismatch`**（canonical · 0-design） |
| mislabel | `cfa_fingerprint_fail` — 非 fingerprint；見 Playbook §3.1a |
| funnel | session=241 → compress=**0** → regime=233 → quiet=240 → attack=**236** → entry=**0** |
| 10–12:30 compress bars | **0 / 36,391** |
| min 30m range_M | 11.0 pt · 門檻 fingerprint ≈4.5–12 pt |
| range_M/ATR p50 | **5.32**（設計隐含 ~0.45） |
| 單根 1m range p50（同窗） | **9.0 pt**（baseline 對齊的是這個） |

**Verdict**：`spec_anchor_mismatch` + `compress_gate_unreachable`

1. **30×1m range** ≠ baseline **單根 1m range** — 量級錯 **~10×**
2. `compress_k∈{0.35,0.45,0.55}` 全年 0 bar；要同定義過關需 **compress_k≈2–4**（診斷 only）
3. 封印 A（attack 當下評估 compress）使 attack 窗波動計入 30m，加劇不可達
4. quiet/attack 極鬆（236/241）vs compress 極嚴（0/241）— **機制互斥**，非 min_stop / 摩擦

**復活路徑**（新 proposal）：單根 compress · 或 quiet_end 評估點 · **禁止** FT-017 事後 tune

---

## 解讀規則

1. verdict **不推翻** MVPClosed  
2. **W900**（= hold 900s）与 **W1800**（legacy gate · 文档常称 W30m）**禁止混读** — 见 §Fingerprint 審計  
3. W900 net median ≤ 0 → 无方向 edge（扣 5 点摩擦）  
4. **`exit_gap` 大 + W900 正** → 考虑 **exit-led / 新 entry+exit FT**（Playbook §5.2），非 grid 改 k  
5. **n=0 + compress_gate=0** → **`spec_anchor_mismatch`**；查 [`GATE_COVERAGE_PREFLIGHT.md`](../docs/features/ai-backtest-tuning/GATE_COVERAGE_PREFLIGHT.md) 附錄 A · gate_report 驗屍 — **禁止** grid 放寬 compress_k 救 n  
6. 詳見 Playbook post_entry 附錄規則
