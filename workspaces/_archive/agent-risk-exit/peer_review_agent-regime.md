# Peer Review — agent-risk-exit 審核 agent-regime

**審核者**：agent-risk-exit（出場與風控調參師）  
**審核對象**：[`../agent-regime/analysis.md`](../agent-regime/analysis.md)  
**日期**：2026-06-27  
**使用模型**：Cursor Agent（senior-trading-professional 視角）

> **限制**：不得跑 sweep、不得改對方 `grid.json`；只質疑與建議。  
> **對照**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)

---

## 1. Grid 邊界與共享假設（≥3 點）

1. **Trend 線互斥合規**：未同開 structure filter，符合 SPEC / ROSTER §5.3。
2. **`trend_filter_enabled: [true]` only**：研究 overlay 合理，但導致 **與 UAT 預設（false）baseline 不對稱** — §2 baseline 用 filter 關、§3 全為 filter 開，對比幅度僅 +0.67 valid_score，解讀價值極低。
3. **strength 0.2–0.6 未產生 veto 分化**：六組 KPI 幾乎相同，grid 可能 **過窄或 backtest 未接 veto 路徑** — 應在 §1 更早聲明「本 grid 為否證實驗」。

---

## 2. Overfitting 自評可信度（≥3 點）

1. **自評 low overfit / none decision value 誠實**：無有效 tune 空間時不應假裝有冠軍 — 對方已明確，可信。
2. **veto_metrics SYNTHETIC**：analysis 正確拒絕用 veto_rate=0% 支持上線；若遺漏此句將構成 **嚴重過度樂觀**，目前已避免。
3. **valid +0.67 vs baseline**：統計與經濟意義皆不足；不應進 leaderboard 作為「次佳軸」與 risk-exit +7.78 相提並論 — 登錄應標註 `research_only` 語意（status 仍可用 valid_submitted）。

---

## 3. 合併上線風險（≥3 點）

1. **開 filter 與出場改善衝突**：risk-exit 冠軍已將 trade_count 降至 113；再疊 trend filter 可能樣本 <20，MDD/QSL 估計不穩。
2. **CAL-8 未過**：TODO §P6-1-CAL 明確；合併 config **不得**含 `trend_filter_enabled: true` 直至 UAT replay。
3. **QSL 32.5% 未改善**：regime 軸未降低秒停損，與本職能（出場/skew）無協同；合併無 Pareto 增益。

---

## 4. 總評

**整體可信度**：**高**（結論保守、符合 CAL 前置）

**一句話摘要**：本輪 regime sweep 為有效否證 — filter 在回測 overlay 下無增量；勿納入 holdout 合併。

**建議**：**維持不推薦** — Phase 4 忽略 regime 參數；待 P6-1-CAL 後再開新 session。
