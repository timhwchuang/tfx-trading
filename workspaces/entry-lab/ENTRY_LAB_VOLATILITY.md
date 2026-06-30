# Entry Lab — 進場時波動／ATR（SSOT）

> **定位**：Entry Lab **進場當下**波動語意的單一真相來源。  
> **上層**：[`ENTRY_LAB_CHARTER.md`](ENTRY_LAB_CHARTER.md) · **方法封印**：[`ENTRY_LAB_PROTOCOL.md`](ENTRY_LAB_PROTOCOL.md)  
> **版本**：v1.0 · 2026-06-30

---

## §0 定位與邊界

本檔回答：**已成交進場**（corpus `entries`）當下的 ATR／波動如何定義、如何分群、如何與 path／contract 分開解讀。

| 本檔是 | 本檔不是 |
|--------|----------|
| corpus 波動欄位字典 | 月度 `stop_ratio` 尺度表（→ [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) §4.1） |
| R4 regime 完整定義 | 月級波動報告（→ [`VOLATILITY_BASELINE.md`](../VOLATILITY_BASELINE.md)） |
| H1／H2 假說與解讀協議 | armed 漏斗指標（→ [`ENTRY_FUNNEL_METRICS.md`](../../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) §4） |
| 探索性 filter 語意 | Playbook grid tune 或 config 建議值 |

**戒律**（複述憲章）：只做**描述 + 分群**；**禁止**輸出可直接寫入 config 的 stop／tp／`min_atr_threshold` 建議值。若假說有方向 → 產 `THESIS_BRIEF` 草稿，promote 須 pre-register 新 FT。

---

## §1 核心張力（H1 vs H2）

高 ATR 進場常同時被解讀為兩件事；**不可混談**。

| ID | 問題 | 若成立 → 含意 |
|----|------|----------------|
| **H1 尺度** | 高波動時，**固定 P0 出場 sim** 的 contract 是否系統性變差？ | path 仍可能正，但 `exit_gap` 偏大 → **出場尺度**與當下波動脫節（對照 SHARED §4.1 `stop_ratio`） |
| **H2 時機** | 高 `atr_percentile_session` 是否代表**波動擴張已發生**、進場偏 late？ | `pct_w900_pos`、`signed_return_over_atr` 在高分位子群衰減；path 與 contract **同步**偏差 → **進場 filter** 假說 |

**MUST**：

- **僅放大 SL／TP 不能解 H2** — 若高分位代表 late entry，拉寬停損只增加成本與回撤，不恢復 edge。
- 高 ATR **不等於** inherently toxic — 須用 path vs contract 分開驗證（§4）。

---

## §2 指標字典（corpus 欄位）

| 欄位 | 定義 | 程式來源 |
|------|------|----------|
| `atr` | 進場當下策略 ATR（與 counterfactual sim 同源） | export / sim row |
| `regime.atr_percentile_session` | 當日 session 內、**截至 `entry_ts` 已收** 1m bar 的 High−Low range 中，`entry_atr` 所處分位（0–100） | `_atr_percentile_session()` · [`entry_lab_regime.py`](../../apps/trading-app/src/reporting/entry_lab_regime.py) |
| `alignment.r4` | `low_vol` if `atr_percentile_session ≤ 50` else `high_vol` | `compute_alignment()` · 同上 |
| `post_entry_forward.W*.signed_return_over_atr` | `close_delta / atr`（該 forward 窗口） | [`post_entry_diagnosis.py`](../../apps/trading-app/src/reporting/post_entry_diagnosis.py) |
| `gross_atr_sim` / `net_atr_sim` | 契約 exit sim 毛／淨點數（名稱反映 ATR-based 出場語意，單位為**點**） | counterfactual export |
| `derived.exit_gap` | `sim_mfe − gross_atr_sim`（契約實現 vs 持倉期 MFE 落差） | [`entry_lab_cohorts.derived_metrics()`](../../apps/trading-app/src/reporting/entry_lab_cohorts.py) |
| `derived.giveback_w5_to_w30` | W300 `close_delta` − W1800 `close_delta`（horizon decay） | 同上 |
| `risk_unit` | 策略結構風險單位（例：FVG 寬度尺度） | sim block（`fvg_mid_trail_sim` 等） |

**常見誤讀**：

- `signed_return_over_atr` 分母是**該筆** `atr`，不是月度 ATR p50。
- `gross_atr_sim` 是點數 PnL，不是「以 ATR 為單位的倍數」。
- ENTRY_FUNNEL_METRICS 的 `signed_return_over_atr` 對象是 **armed** cohort；本檔對象是 **entered** corpus。

---

## §3 Regime R4（操作化）

| 項目 | 封印值 |
|------|--------|
| Confirmatory 二分 | `atr_percentile_session ≤ 50` → `low_vol`（順勢語意見 PROTOCOL Long 列） |
| Lookahead | **禁止** — 只用 `entry_ts` 前已收 1m bar（與 R1–R3 一致） |
| 閾值變更 | **MUST** bump [`ENTRY_LAB_PROTOCOL.md`](ENTRY_LAB_PROTOCOL.md) version |

**探索性三分**（非 confirmatory 門檻；樣本 n 分級仍適用 PROTOCOL §樣本分級）：

| Bucket | 條件 | 用途 |
|--------|------|------|
| `low` | ≤ 50 | 對齊 R4 confirmatory |
| `mid` | 50 &lt; x ≤ 80 | 過渡帶 |
| `high` | &gt; 80 | 測試 H2（late／擴張後進場） |

---

## §4 解讀協議（Path vs Contract）

| 平面 | 定義 | 主要欄位 |
|------|------|----------|
| **Path** | stop-less 進場後價格路徑 | `post_entry_forward`、`pct_w900_pos`、`signed_return_over_atr` |
| **Contract** | 封印 P0 exit sim 契約 PnL | `gross_atr_sim`、`net_atr_sim`、`exit_gap` |

**高波動子群**（`high_vol` 或 `high` bucket）解讀矩陣 — **MUST 分開報 path 與 contract**：

| Path | Contract | `exit_gap` | 解讀 |
|------|----------|------------|------|
| 正 | 負 | 大 | 支持 **H1**（尺度／出場 sim 與波動脫節） |
| 負或衰減 | 負 | 任意 | 支持 **H2**（進場時機／延續性問題） |
| 正 | 正 | 小 | 高波動**非** inherently toxic |
| 正 | 負 | 小 | 檢查摩擦、`net_atr_sim`；可能樣本或 sim 細節 |

`giveback_w5_to_w30` 偏大 → horizon decay 快，可輔助 H2（順勢脈衝短）。

---

## §5 與月度尺度的關係

| 維度 | 月度尺度 | 進場當下（本檔） |
|------|----------|------------------|
| 問題 | 固定點數 HS／trail／TP 相對**當月** ATR 是否過緊 | 該筆進場處於**當日 session** 波動分位的哪裡 |
| 指標 | `stop_ratio`、`trail_ratio`、`tp_ratio` | `atr_percentile_session`、`alignment.r4` |
| SSOT | [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) §4.1 · [`VOLATILITY_BASELINE.md`](../VOLATILITY_BASELINE.md) | **本檔** |

- `min_atr_threshold`：平淡市**拒絕武裝／進場**（策略進場前濾網）。
- R4／`atr_percentile_session`：已進場樣本的 **regime 背景**（事後分群，非同一道門）。

兩者並列才能解釋「月級停損偏緊」與「進場當下是否已是波動高峰」是否同時成立。

---

## §6 探索性 filter（Lab 合法）

實作：[`entry_lab_reports.build_intersection_filters()`](../../apps/trading-app/src/reporting/entry_lab_reports.py)

| Filter | 條件 | Slug |
|--------|------|------|
| `gap_atr_high` | `abs(gap_pts) / atr ≥ 1.0` | GDC、GUDT |
| `risk_unit_low` | `risk_unit ≤ 12.0` | FRP、SFBT |

另見全 slug：`structure_long`、`r2_with_trend`（結構／趨勢，非純波動）。

**邊界**：filter 交集探索在 Lab **合法**（憲章 §與 Playbook 邊界）；寫入 gate 或改 grid **禁止**，須 pre-register 新 FT 重評。

---

## §7 Promotion 出口

| 診斷結論 | 下一步 |
|----------|--------|
| H1 為主（path 正、exit_gap 大） | `THESIS_BRIEF` 草稿 → 出場尺度 FT 或 VOLATILITY_BASELINE 敘事延伸 |
| H2 為主（path 衰減、高分位差） | `THESIS_BRIEF` 草稿 → 進場 filter／regime FT + gate 重評 |
| 子群 n &lt; 15 | 僅假說生成；不得 confirmatory 宣稱（PROTOCOL §樣本分級） |
| 符合 PROTOCOL §Promotion 1–4 | 人類 §Decision 後進 Playbook |

**MUST NOT**：在本軌直接輸出「ATR&gt;80 時 stop=12」類 config；尺度 redesign 屬 Playbook／新 FT 範疇。
