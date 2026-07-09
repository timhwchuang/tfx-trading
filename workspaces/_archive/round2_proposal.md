# Round 2 提案 — 出場尺度（FT-003）

**狀態**：**已否決**（2026-06-27 · [`strategy_diagnosis.md`](strategy_diagnosis.md) §Decision Option A）— 不執行 sweep  
**依據**：[`strategy_diagnosis.md`](strategy_diagnosis.md) · [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) · Phase 3.6  
**執行 agent**：`agent-risk-exit`（出場主導；進場／執行鎖定）

---

## 1. 為什麼要第二輪

| 現象 | 實務解讀 |
|------|----------|
| 四平面 valid 冠軍 **淨期望全負** | 本輪 grid 在錯的維度上已搜完，勿再放大笛卡爾積 |
| conservative 毛點略正、淨點大負 | 摩擦 5 點/趟 + 出場過緊，不是單調進場 band |
| QSL 28–33%（baseline） | `hard_stop=6` 落在 1m 噪音內 |
| 4 月 ATR p50≈25.7，`stop_ratio`≈23% | 硬停僅約 0.23×ATR，偏緊 |

**本輪只回答一個問題**：把 **硬停／trail／TP** 放到與 ATR 相称的尺度後，valid **淨期望** 能否轉正或至少 **QSL 明顯下降且 gross 改善**。

---

## 2. 鎖定參數（Round 1 結論，本輪不 sweep）

來自已完成 sweep 冠軍（寫入 `agent-risk-exit/config/config.yaml`）：

| Key | 鎖定值 | 來源 |
|-----|--------|------|
| `entry_band_points` | **2.5** | agent-conservative 冠軍 |
| `min_atr_threshold` | **25** | agent-conservative 冠軍 |
| `ioc_slippage_points` | **3** | agent-execution 冠軍 |
| `max_consecutive_loss` | **4** | 預設（本輪 grid 不 tune） |
| `max_daily_loss_points` | **120** | 禁止為 PnL 放大 |

---

## 3. Round 2 grid（`agent-risk-exit/grid.round2.json`）

```json
{
  "hard_stop_points": [10, 12, 14, 16],
  "trail_points": [6, 8],
  "fixed_tp_points": [20, 24]
}
```

- **16 combos**（≤36）· **3 keys**（≤4）
- `trail=6` 納入：execution 已證實較 8/10 降 QSL

### 預期 stop_ratio（4 月 valid，ATR p50≈25.7）

| hard_stop | stop_ratio | 解讀 |
|-----------|------------|------|
| 10 | ~39% | 仍偏緊，對照組 |
| 12 | ~47% | 接近 0.5×ATR |
| 14 | ~54% | 主探索帶 |
| 16 | ~62% | 較寬，看 QSL↓ vs 單筆虧損↑ |

重跑 `ft003_volatility_baseline.py` 可驗證各月 ratio（診斷 only，不選參）。

---

## 4. 假說與否證標準

**假說**：`hard_stop` 提至 10–16 後，QSL 自 ~30% 降至 **<20%**，且 valid **gross expectancy** 不惡化；若 net 仍全負但 gross 轉正 → 下一輪再碰執行／進場，而非再加 hard_stop。

| 結果 | 判定 |
|------|------|
| 16 組 net exp 全 < 0，gross 仍 ≤ 0 | 策略邏輯失敗 → 停 sweep，改進場或降頻 |
| gross > 0 但 net < 0 | 出場尺度部分成立 → 可微調 TP／摩擦假設 |
| 任一組 net > 0 且 QSL < 25% | 候選進 Phase 4 holdout（仍須一次 5 月檢定） |
| valid 正、holdout 崩 | `overfit_suspect` |

**排名**：仍以 `valid_score`（net expectancy − QSL 懲罰）為主；`analysis.md` **必須** 另報 gross expectancy，勿只看 composite。

---

## 5. 批准後執行步驟

```powershell
cd c:\Users\Tim\Desktop\tfx-trading\apps\trading-app\src
$env:PYTHONPATH="."
$env:CONFIG_PATH="c:\Users\Tim\Desktop\tfx-trading\workspaces\agent-risk-exit\config\config.yaml"

# 1) overlay smoke（每個 grid key）
python -m sweep.overlay_smoke

# 2) 啟用 round2 grid
Copy-Item ..\..\..\workspaces\agent-risk-exit\grid.round2.json `
  ..\..\..\workspaces\agent-risk-exit\grid.json

# 3) sweep（建議備份 round1 結果）
Rename-Item ..\..\..\workspaces\agent-risk-exit\sweep_result.jsonl sweep_result.round1.jsonl -ErrorAction SilentlyContinue
python scripts\ft003_run_sweep.py agent-risk-exit

# 4) 填 analysis.md → peer_review → leaderboard（本輪 risk-exit 一筆）
```

產物寫入 `sweep_result.jsonl`（**勿**與 round1 混讀）。

---

## 6. 禁止事項

- 用 2026-05 統計回頭改 grid（SPEC §4.6）
- 同 session 看了 valid 再改 `grid.json` 重跑
- 為刷正期望加入 `entry_band` / `min_atr` / `ioc` keys（屬其他 agent）
- 未批准即 append `leaderboard` 或產 `elected_config.yaml`

---

## §Approval（人類簽核）

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | **驳回** |
| 備註 | gross ≈ 0、§6 逆向選擇；出場 grid 無法解題。改策略 thesis 重設計。 |
