# Analysis — agent-conservative（資本保全調參師）

**Agent**：agent-conservative  
**Role**：資本保全調參師  
**分析日期**：2026-06-27  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04（Holdout 2026-05 封印）  
**Sweep 執行模型**：`ft003_run_sweep.py`（bulk，`run_id` d36002bdb949）  
**分析撰寫模型**：Cursor Agent（senior-trading-professional 視角）

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §2  
> **日期切分**：[`DATA_SPLIT.md`](../DATA_SPLIT.md)

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：在控制 MDD 與秒停損的前提下，提升 valid 區間淨期望的穩定性；寧可少交易，避免平淡市況與假 pullback 磨損。

**本次調參假說**：提高 `min_atr_threshold` 並適度調整 `entry_band_points`，可過濾低波動假突破，使 QSL ↓、MDD 可控；代價是交易次數下降。

**選擇這些 grid 邊界的理由**（對照 SHARED_ASSUMPTIONS §4–§5）：

- `min_atr_threshold` 22–28：微台 Q1/Apr 常見低 ATR 平淡段；高於 repo 預設 25 測「更嚴」、低於 25 測「是否過濾過頭」。
- `entry_band_points` 1.5–2.5：pullback 寬緊直接影響 near-VWAP 進場率；1.5 測資本保全「收緊」、2.5 測是否窄 band 在 4 月造成過多假訊號。
- 未 tune 出場／執行 keys（屬 #2/#3 agent），符合 ROSTER §2.4。

**預期參數交互**（≥2 組）：

- `entry_band_points` ↓ × `min_atr_threshold` ↑ → 雙重收緊，預期 trade_count 非線性下降、QSL 可能反升（錯過趨勢後被迫在劣質點進場）。
- `entry_band_points` ↑ × `min_atr_threshold` = 25 → 預期保留足夠樣本下 QSL 改善（本次 sweep 主效應）。

**預期 Trade-off**：犧牲部分進場機會（或相反：放寬 band 增加樣本），換取較低秒停損與較穩定 valid 曲線。

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | -21.99 | expectancy_net − sl_penalty×QSL |
| daily_pnl_points | -48.0 | valid 區間毛點數合計（20 日） |
| expectancy_net | -5.32 | 摩擦 5 點/趟後 |
| sharpe_net | -0.60 | per_trade（全期 round-trip） |
| max_drawdown_points | 798.0 | 累積淨 MDD |
| quick_stop_loss_rate | 33.3% | 50/150；高於 Pilot 觀測門檻 |
| trade_count | 150 | exit 數 |
| day_count | 20 | 2026-04 全月 |

**交易員一句話評論**：樣本量足（日均約 7.5 筆），但預設參數在 4 月淨期望為負、秒停損率偏高；正是資本保全軸（收緊 band / 提高 ATR 門檻）該驗證的假設場景。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否

---

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | vs Baseline | 代價 |
|------|-------------|--------|-------------|------|
| 1 | -18.83 | `entry_band_points: 2.5`, `min_atr_threshold: 25` | valid_score **+3.16**；QSL 27.8%（↓5.5pp）；expectancy_net -4.94（↑0.38/趟）；valid 毛 PnL **+10**（baseline -48） | train valid_score -21.65、train 淨 -1990.5；valid 筆數 162（↑12） |
| 2 | -19.04 | `entry_band_points: 2.5`, `min_atr_threshold: 22` | +2.95；QSL 28.2%；expectancy_net -4.96 | ATR 門檻較鬆 → valid 174 筆、淨期望略差於 #1 |
| 3 | -19.57 | `entry_band_points: 2.5`, `min_atr_threshold: 28` | +2.42；QSL 28.9%；筆數 149（↓1） | 過濾偏嚴，valid 毛 PnL 仍負（-21） |

**最差 1 組**：`entry_band_points: 1.5`, `min_atr_threshold: 28` — valid_score **-23.72**（比 baseline 差 1.73）；QSL **36.1%**、expectancy_net -5.68。窄 band + 高 ATR 雙重收緊，樣本與品質皆惡化。

**參數敏感度**：

- **entry_band_points**：2.5 包辦 top-3；1.5 組全部落在後段（valid_score -21.8～-23.7）。放寬進場帶是本次 sweep 主效應。
- **min_atr_threshold**：在 band=2.5 下，22→25→28 呈現「中等門檻最佳」；28 減筆但未換來更好 valid_score。
- **交互**：窄 band（1.5）對 ATR 調整不敏感且普遍差；寬 band（2.5）才讓 ATR=25 的資本保全濾網發揮作用。

**最有價值的一個發現**：**加寬 entry band 至 2.5 並維持 ATR≥25**，可在 valid 讓毛點數轉正並壓低秒停損率；但 **九組淨期望仍全負**——進場濾網平面內有相對排序，無絕對可行解。

### 摩擦對策略的實際影響（SHARED_ASSUMPTIONS §3.1）

- 冠軍 valid：毛 +10 點、淨 **-800** 點；162 趟 × 5 點/趟 ≈ **810** 點摩擦，幾乎吃掉全部 gross edge。
- 提高 `min_atr_threshold` 減筆（149～174）**不足以**把淨期望拉正；問題核心是 **每趟 gross expectancy 接近零**，非單純「交易太頻繁」。
- 扣摩擦後 break-even 需平均獲利結構明顯優於現況（勝率 ~33%、均損主導）；本 grid **無法**靠兩個進場 knob 達成。

*Sweep 產物：`sweep_result.jsonl`（9 組，bulk ~35min，`run_id` d36002bdb949）*

---

## 4. Overfitting 與穩健性評估

**Train vs Valid**（冠軍 `2.5 / 25`）：

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| daily_pnl_points | -410.5 | +10.0 | valid 優於 train | 非典型；可能 Q1 市況更差或 4 月 regime 偏好 |
| expectancy_net | -6.30/趟 | -4.94/趟 | valid 較好 ~1.4 點/趟 | 相對改善仍 **全為負** |
| max_drawdown_points | 2028.5 | 832.0 | valid MDD 較低 | 冠軍 valid MDD 略差於 baseline（832 vs 798） |
| quick_stop_loss_rate | 30.7% | 27.8% | 同向改善 | QSL 仍偏高；出場軸未 tune |
| trade_count | 316 | 162 | — | 樣本充足（valid ≥20） |

**Overfitting 風險**：**中**

**理由**：

1. **非**「train 賺 valid 虧」的經典 overfit，但 valid 優於 train 也可能是 **4 月單月運氣**，5 月 holdout 可能反轉。
2. 全 grid 淨期望為負，不存在「刷亮 valid」的強誘因，但 **相對冠軍** 仍可能對 4 月過度適配（band=2.5 主效應）。

**Holdout 風險因子**（不得引用 5 月實數）：

- 5 月若波動結構類似 Q1（低 ATR、震盪），冠軍組合可能回到 train 深度虧損區間。
- 秒停損結構未調；若 5 月流動性變差，QSL 可能再升、淨期望更差。
- 毛點轉正對摩擦極敏感；略差的 fill 假設即可把 +10 毛點打回負值。

**整體穩健性**：grid 內 **相對最佳** 有統計意義（樣本足、主效應一致），但 **絕對績效不合格**；不宜視為穩健獲利參數，僅作「進場濾網平面的否證／部分證實」。

---

## 5. 推薦與下一步

- [ ] 建議進入 Holdout 候選  
- [x] **不推薦**

**主因**：九組 `valid_score` 全負、冠軍淨期望 **-4.94/趟**；摩擦主導虧損，進場濾網無法產出可行解。本 agent **不建立** `elected_config.yaml`。若 Phase 4 仍堅持以本 grid 冠軍跑 holdout 且結果為負 → 建議標 **`overfit_suspect`** 或 **`grid_no_viable_solution`**（非策略邏輯單點失敗，而是本軸無法拉正淨期望）。

**Grid 內相對最佳（僅供 leaderboard / 交叉比對，非當選）**：

```yaml
relative_best_params:
  entry_band_points: 2.5
  min_atr_threshold: 25
```

**為什麼不推薦 holdout**：valid 毛點轉正不等於淨獲利；train 區間深度虧損；QSL 28% 仍高；出場／執行未在本輪覆蓋。應等 `agent-execution` sweep 與人類 Phase 4 決策，而非以本結果單獨晉級。

### 協作備註

- `leaderboard.jsonl` 已 append `valid_submitted`（valid_score -18.83，trade_count 162）。
- **未**產出 `elected_config.yaml`（刻意；見上）。
- 建議 execution agent peer_review 時質疑：QSL 瓶頸是否在 `trail_points` / `hard_stop`，而非進場 band。
- Phase 1 Pass 後：`compare_fill_audits` 再評估摩擦假設。

### 免責與人類決策權

- 本分析 **不** 構成 Pilot / Live Ready。  
- Holdout（2026-05）：Phase 4 前填「未跑」。  
- Overfitting 自評摘要：**medium** — valid 優於 train 但全 grid 淨負；holdout 權重應高於 valid 毛點轉正。

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [x] 已確認與 SHARED_ASSUMPTIONS v1.1 及 PLAN 一致
- [x] 已完成 peer_review（`peer_review_agent-execution.md`）
- [x] 已回覆 peer_review 質疑（若有）

**回覆摘要**：execution 質疑「窄 band 是否過度保守」— 維持不推薦 holdout；同意出場/trail 軸優先於進場濾網。見 `peer_review_agent-execution.md` §4。
