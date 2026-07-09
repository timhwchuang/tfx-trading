# Peer Review — agent-conservative 審核 agent-execution

**審核者**：agent-conservative（資本保全調參師）  
**審核對象**：[`../agent-execution/analysis.md`](../agent-execution/analysis.md)  
**日期**：2026-06-27  
**使用模型**：Cursor Agent（senior-trading-professional 視角）

> **限制**：不得跑 sweep、不得改對方 `grid.json`；只質疑與建議。  
> **對照**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)

---

## 1. Grid 邊界與共享假設（≥3 點）

1. **IOC 2–4 與 live ±3 底線**：grid 含 `ioc_slippage_points: 4` 的組合 valid_score 明顯惡化（#3 僅 -18.34），但 analysis 冠軍選 IOC=3 而非 2，應在 §3 更明確說明「2 vs 3 差距 <0.04 valid_score」以免 Phase 4 合併時誤選更激進讓價。
2. **trail 與 risk-exit 重疊**：execution 與 risk-exit 皆 tune `trail_points`；合併 config 時若兩軸都寫入 `trail_points: 6` 語意上無衝突，但 **無法分辨改善歸因** — 建議 §5 協作備註標註「trail 歸 risk-exit 主導」。
3. **未含 `pending_timeout_sec`**：ROSTER §3.4 允許 1–3s；回測影響有限但 UAT 對照是執行職能核心。單輪 sweep 可接受，但 §1 應註明「留待 Phase 1 fill audit」而非省略。

---

## 2. Overfitting 自評可信度（≥3 點）

1. **自評「中」合理**：QSL 17.9%→19.3% train/valid 同向，非典型 overfit；但 valid 淨期望 **劣於** train（-6.48 vs -6.01），analysis 已揭露，可信。
2. **valid_score +5.85 的誘惑**：改善主要來自 QSL penalty 項；毛 PnL 從 -48 惡化至 -221.5（冠軍組）。審核者同意對方「不單獨 holdout」結論，避免被 composite 誤導。
3. **樣本量 150 筆充足**：無 `insufficient_sample` 疑慮；但若與 conservative 寬 band 合併後筆數變化，應在 Phase 4 重算門檻。

---

## 3. 合併上線風險（≥3 點）

1. **MockBroker vs live**：§3 已提 callback 延遲風險；合併 config 若採 IOC=3，live 仍受 ±3 風控約束，回測假設可能 **高估** 成交品質。
2. **trail=6 雙軸重複**：與 risk-exit 冠軍相同；合併時只應保留一處出處，否則 election_report 難以審計參數來源。
3. **與進場濾網交互未測**：execution sweep 在預設進場參數上跑；若合併 `entry_band_points: 2.5`，QSL/筆數可能非線性變化 — Phase 4 holdout 應用 **合併後** config 一次跑，非各軸冠軍簡單拼接未驗證。

---

## 4. 總評

**整體可信度**：**中～高**（分析誠實、結論保守）

**一句話摘要**：執行軸證實 trail 是 QSL 主因，但無法拉正淨期望；宜作合併候選的 IOC knob，trail 歸 risk-exit。

**建議**：**維持** — 同意不單獨 holdout；要求 Phase 4 合併 config 時註明 trail 歸屬。
