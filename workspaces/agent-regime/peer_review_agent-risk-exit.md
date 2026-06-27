# Peer Review — agent-regime 審核 agent-risk-exit

**審核者**：agent-regime（市況濾網研究員）  
**審核對象**：[`../agent-risk-exit/analysis.md`](../agent-risk-exit/analysis.md)  
**日期**：2026-06-27  
**使用模型**：Cursor Agent（senior-trading-professional 視角）

> **限制**：不得跑 sweep、不得改對方 `grid.json`；只質疑與建議。  
> **對照**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)

---

## 1. Grid 邊界與共享假設（≥3 點）

1. **fixed_tp 18–26 / trail 6–10 / mcl 3–5**：符合 ROSTER §4.3；未含 `hard_stop_points`（Round 2 only），合規。
2. **27 combos ≤ 36 上限**：笛卡爾積合理；最差組（tp26/trail10/mcl5）提供有用邊界警示，grid 設計品質高。
3. **未放大 max_daily_loss_points**：符合禁止條款；風控底線未動。

---

## 2. Overfitting 自評可信度（≥3 點）

1. **train/valid 同向改善 QSL 與 MDD**：自評 low-medium 有數據支撐；非單月刷分型態。
2. **valid_score -14.21 仍為負**：analysis 未宣稱獲利，建議 holdout **候選**而非 Pilot Ready — 尺度正確。
3. **trade_count 113**：仍 ≥20；但若 5 月低波動月筆數骤降，應預留 `insufficient_sample` 路徑 — §4 已提及。

---

## 3. 合併上線風險（≥3 點）

1. **trail=6 與 execution 重疊**：對方 §5 已要求合併時單一歸屬；regime 視角同意，避免參數審計模糊。
2. **未測 regime × exit 交互**：緊 trail 在 trend 強/弱月表現可能不同；本輪未跑交叉 grid（規則允許），holdout 一次跑合併 config 即可，但 **不可**事後用 5 月結果再加 tune。
3. **mcl=3 心理底線**：實盤連虧 3 次停玩可能錯過 V 反；屬策略設計取捨，非 overfit，但人類簽核時應知悉。

---

## 4. 總評

**整體可信度**：**高**

**一句話摘要**：四軸中最強信號；建議作 Phase 4 合併 holdout 出場主軸，但勿與未校準 trend filter 同開。

**建議**：**維持 holdout 候選** — regime 軸不參與合併；出場參數可進 election。
