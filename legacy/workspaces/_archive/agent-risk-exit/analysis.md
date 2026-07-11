# Analysis — agent-risk-exit（出場與風控調參師）

**Agent**：agent-risk-exit  
**Role**：出場與風控調參師  
**分析日期**：2026-06-27  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04（Holdout 2026-05 封印）  
**Sweep 執行模型**：`ft003_run_sweep.py`（bulk，`run_id` 8fb34c19bba8）  
**分析撰寫模型**：Cursor Agent（senior-trading-professional 視角）

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §4

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：優化固定 TP、trail 與連虧熔斷的組合，改善 **skew**（贏家拿得住、輸家夠短），在 `max_daily_loss_points` 不變前提下壓 MDD 與 QSL。

**本次調參假說**：預設 trail=8 過寬導致秒停損；收緊至 6 並配合較高 `fixed_tp_points`（26）可拉長贏家、縮短連虧尾部；`max_consecutive_loss=3` 優於 4–5（少交易、較低 MDD）。

**選擇這些 grid 邊界的理由**（對照 SHARED_ASSUMPTIONS §7；skew / 連虧心理底線）：

- `fixed_tp_points` 18–26：微台點值下測「短贏」vs「中等 TP」對勝率與 MDD 的權衡。
- `trail_points` 6–10：與 execution agent 對齊；6 為緊追蹤、10 測寬 trail 災難區（最差組合）。
- `max_consecutive_loss` 3–5：心理底線；5 允許更多連虧後再進場 → 交易數 ↑、MDD ↑。

**預期參數交互**（≥2 組）：

- `trail_points` ↑ × `fixed_tp_points` 高 → QSL 急升、valid_score 崩潰（已驗證）。
- `max_consecutive_loss` ↑ × `trail_points`=6 → 筆數增加但 expectancy 惡化（4–5 組均劣於 3）。

**預期 Trade-off**：緊 trail + 高 TP 減少交易次數（113 vs baseline 150），換取較低 QSL 與較淺 valid MDD。

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | -21.99 | expectancy_net − sl_penalty×QSL |
| daily_pnl_points | -48.0 | valid 區間毛點數合計（20 日） |
| expectancy_net | -5.32 | 摩擦 5 點/趟後 |
| sharpe_net | — | per_trade |
| max_drawdown_points | 798.0 | 累積淨 MDD |
| quick_stop_loss_rate | 33.3% | |
| trade_count | 150 | exit 數 |
| day_count | 20 | 2026-04 全月 |

**交易員一句話評論**：預設 config 基線已建立；valid_score -21.99，QSL 33.3%，樣本 150 筆。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | max_drawdown_points | quick_stop_loss_rate | vs Baseline |
|------|-------------|--------|---------------------|----------------------|-------------|
| 1 | -14.21 | `{'fixed_tp_points': 26, 'trail_points': 6, 'max_consecutive_loss': 3}` | 655.5 | 16.8% | **+7.78** |
| 2 | -14.28 | `{'fixed_tp_points': 22, 'trail_points': 6, 'max_consecutive_loss': 3}` | 663.5 | 16.8% | **+7.71** |
| 3 | -14.63 | `{'fixed_tp_points': 18, 'trail_points': 6, 'max_consecutive_loss': 3}` | 711.5 | 17.1% | **+7.36** |

**最差 1 組**：`{'fixed_tp_points': 26, 'trail_points': 10, 'max_consecutive_loss': 5}` — valid_score **-24.91**；MDD 1016.5。

**參數敏感度**：

- **trail_points**：=6 包辦 top-9 中前段；=10 與高 TP 疊加為最差區（valid_score -24.91、QSL 39%）。主效應最強。
- **fixed_tp_points**：在 trail=6、mcl=3 下，26 > 22 > 18（valid_score -14.21 / -14.28 / -14.63）；較高 TP 略優，但差距小於 trail 效應。
- **max_consecutive_loss**：3 全面優於 4–5；放寬連虧上限增加 churn、MDD 放大，不符合風控職能。

**最有價值的一個發現**：**trail=6 + fixed_tp=26 + mcl=3** 是四軸 sweep 中 **valid_score 最佳（-14.21）**；QSL 16.8%、valid MDD 655（↓18% vs baseline），勝率升至 37.2%。出場結構是 MVP 期間最有訊號的調參平面，但仍 **淨負 -5.80/趟**。

## 4. Overfitting 與穩健性評估

**Train vs Valid**（冠軍 `fixed_tp_points: 26`, `trail_points: 6`, `max_consecutive_loss: 3`）：

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| max_drawdown_points | 1519.0 | 655.5 | valid 顯著較低 | MDD 改善在 valid 可重現 |
| expectancy_net | -6.10/趟 | -5.80/趟 | valid 略好 | 仍為負；方向一致 |
| daily_pnl_points | -274.0 | -90.5 | valid 毛損較小 | 非典型 overfit 型態 |
| quick_stop_loss_rate | 19.7% | 16.8% | 同向改善 | QSL 結構穩健 |
| trade_count | 249 | 113 | ↓37% | 仍 ≥20；密度下降需 holdout 驗證 |

**Overfitting 風險**：**低～中**

**理由**：

1. Train/valid **同向改善** QSL 與 MDD，非「valid 單月刷分」典型型態。
2. 交易數降至 113 仍達門檻，但若 holdout 筆數 <20 則統計不足。

**Holdout 風險因子**（不得引用 5 月實數）：

- 5 月若趨勢延續性強，緊 trail 可能過早出場、錯過尾部獲利。
- `max_consecutive_loss=3` 在劇烈震盪月可能過早停玩，錯過反轉段。
- 與 execution 同設 `trail_points=6` 時，合併 config 須確認無雙重疊加效應。

**整體穩健性**：四軸中 **相對最強**；建議作 Phase 4 **合併 holdout 候選的主出場軸**，但仍須 holdout 驗證淨期望方向。

---

## 5. 推薦與下一步

- [x] **建議進入 Holdout 候選**（合併 config 出場軸；非單 knob Pilot）  
- [ ] 不推薦

**推薦配置（合併選舉用）**：

```yaml
recommended_params:
  fixed_tp_points: 26
  trail_points: 6
  max_consecutive_loss: 3
```

**為什麼推薦**：四軸 valid_score 最高（-14.21）、QSL 與 MDD 同步改善、train/valid 方向一致。雖淨期望仍負，但是 **Phase 4 合併 holdout 的首選出場參數**；須與 conservative 進場、execution IOC 合併後一次跑 5 月。

### 協作備註（與 agent-execution 的 trail 邊界、conservative 的進場密度）

- `trail_points=6` 與 execution 冠軍重疊 — 合併時 **只保留本軸 trail**，execution 僅貢獻 `ioc_slippage_points: 3`。
- 交易數 113 低於 baseline；若合併 conservative `entry_band_points: 2.5` 須監控樣本量。
- 已撰寫 `peer_review_agent-regime.md`；regime 軸幾乎無增量，不應在合併 config 開 trend filter。

### 免責與人類決策權

- 本分析 **不** 構成 Pilot / Live Ready。Holdout：未跑。未放大 `max_daily_loss_points`。
- Overfitting 自評摘要：**low-medium** — 結構改善可重現，絕對 PnL 仍負。

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [x] 已確認與 SHARED_ASSUMPTIONS v1.1 及 PLAN 一致
- [x] 已完成 peer_review（`peer_review_agent-regime.md`）
- [x] 已回覆 peer_review 質疑（若有）

**回覆摘要**：regime 質疑 filter 無 veto — 同意本輪不納入合併 config；出場軸獨立 holdout 候選。
