# Analysis — agent-execution（執行品質調參師）

**Agent**：agent-execution  
**Role**：執行品質調參師  
**分析日期**：2026-06-27  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04（Holdout 2026-05 封印）  
**Sweep 執行模型**：`ft003_run_sweep.py`（bulk，`run_id` 7d1d322fbb97）  
**分析撰寫模型**：Cursor Agent（senior-trading-professional 視角）

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §3  
> **執行落差**：[`packages/trading-backtest/SPEC.md`](../../packages/trading-backtest/SPEC.md) §8–§9

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：在 MockBroker 固定滑價假設下，調整 IOC 讓價與 trail 寬度，壓低 **quick_stop_loss_rate** 並改善 valid 淨期望；同時記錄與 live callback 延遲的落差風險。

**本次調參假說**：`trail_points` 過寬會把停損變成「秒停損」；適度收緊 trail（6）並維持 IOC 2–3 點讓價，可在不犧牲過多成交的前提下顯著降低 QSL。

**選擇這些 grid 邊界的理由**（對照 SHARED_ASSUMPTIONS §3；IOC ±3 live 底線）：

- `ioc_slippage_points` 2–4：微台回測 tier 研究區間；2 點接近 live 風控底線意識，4 點測「摩擦過大」上界。
- `trail_points` 6–10：repo 預設 8；6 測緊追蹤、10 測寬 trail 對 QSL 的惡化（與 risk-exit agent 的 trail 軸對照）。
- 未 tune `pending_timeout_sec`（本輪 grid 僅 2 keys）；留 Phase 1 `compare_fill_audits` 對照。

**預期參數交互**（≥2 組）：

- `trail_points` ↑ × `ioc_slippage_points` 固定 → QSL 非線性上升（寬 trail 放大停損觸發）。
- `ioc_slippage_points` ↑ × `trail_points`=6 → 成交改善有限但 QSL 與淨期望惡化（高摩擦疊加）。

**預期 Trade-off**：壓低 QSL 可能縮小單筆獲利尾部（trail 過緊）；若 MDD 同步上升則視為假優化。

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | -21.99 | 與 conservative 相同預設起點 |
| daily_pnl_points | -48.0 | valid 區間毛點數合計 |
| expectancy_net | -5.32 | |
| max_drawdown_points | 798.0 | |
| quick_stop_loss_rate | 33.3% | sweep 主戰場 |
| trade_count | 150 | |
| day_count | 20 | |

**交易員一句話評論**：預設 config 下執行面問題明顯（秒停損 1/3、trail 出場幾乎打平）；`ioc_slippage_points` / `trail_points` grid 有明確改善空間，樣本量已夠。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否

---

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | quick_stop_loss_rate | vs Baseline |
|------|-------------|--------|----------------------|-------------|
| 1 | -16.14 | `{'ioc_slippage_points': 3, 'trail_points': 6}` | 19.3% | valid_score **+5.85** |
| 2 | -16.18 | `{'ioc_slippage_points': 2, 'trail_points': 6}` | 19.2% | valid_score **+5.81** |
| 3 | -18.34 | `{'ioc_slippage_points': 4, 'trail_points': 6}` | 23.5% | valid_score **+3.65** |

**最差 1 組**：`{'ioc_slippage_points': 4, 'trail_points': 10}` — valid_score **-25.74**；QSL 41.3%。

**參數敏感度**：
- **ioc_slippage_points**：2→3 在 trail=6 時 QSL 略升但 valid_score 接近；4 點摩擦過大，#1 落在 IOC=2。
- **trail_points**：同一 IOC 下 6 < 8 < 10（valid_score）；trail 放寬明顯推高秒停損率。
- **交互**：低 IOC + 緊 trail（2/6）為最佳執行組合；高 trail 與高 IOC 疊加最差。

**最有價值的一個發現**：**IOC=3、trail=6** 將 valid QSL 從 33.3% 壓到 **19.3%**，valid_score 提升 **+5.85**；trail=6 是主效應、IOC 2 vs 3 差距極小。證實「寬 trail 是秒停損主因」，但淨期望仍 **-6.48/趟**，需與 risk-exit 出場軸合併評估。

### 摩擦對策略的實際影響（SHARED_ASSUMPTIONS §3.1）

- 冠軍 valid：毛 -221.5 點、淨 **-971.5** 點；150 趟 × 5 點 ≈ 750 點固定摩擦，外加滑價 tier 與 QSL 結構損失。
- 壓低 QSL **改善 composite**，但未扭轉「每趟 gross edge 不足」；執行面 alone 無法拉正淨期望。
- Live 若 callback 延遲 > 回測假設，實際 QSL 可能高於 19.3%；Phase 1 後須 `compare_fill_audits` 校準。

*Sweep 產物：`sweep_result.jsonl`（9 組，bulk ~35min）*

## 4. Overfitting 與穩健性評估

**Train vs Valid**（冠軍 `ioc_slippage_points: 3`, `trail_points: 6`）：

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| quick_stop_loss_rate | 17.9% | 19.3% | 同向、略升 | 改善結構在 valid 仍成立（遠低於 baseline 33%） |
| expectancy_net | -6.01/趟 | -6.48/趟 | valid 略差 | 淨期望仍深度為負 |
| daily_pnl_points | -310.0 | -221.5 | valid 毛損較小 | 非「train 賺 valid 虧」型 overfit |
| max_drawdown_points | 1845.0 | 971.5 | valid MDD 較低 | 冠軍 valid MDD 高於 baseline 798（trail 收緊副作用） |
| trade_count | 307 | 150 | — | 樣本充足 |

**Overfitting 風險**：**中**

**理由**：

1. QSL 改善在 train/valid **方向一致**，非單月刷分；但 valid_score 提升主要來自 penalty 項，毛 PnL 仍惡化。
2. `trail_points`=6 與 risk-exit 冠軍重疊 — 合併 config 時須避免 **重複 tune 同一 knob**（見 peer_review）。

**Holdout 風險因子**（不得引用 5 月實數）：

- 5 月若波動放大，緊 trail 可能增加 whipsaw、QSL 反彈。
- MockBroker next-tick fill 可能 **低估** live 滑價；holdout 若 QSL 回到 25%+，執行假設需下修。
- 與 conservative 進場濾網合併後 trade_count 可能下降，統計噪音上升。

**整體穩健性**：執行軸內 **相對最佳明確**（trail 主效應穩定），但 **絕對績效不合格**；宜作 Phase 4 合併候選的一個 knob，不宜單獨 holdout 晉級。

---

## 5. 推薦與下一步

- [ ] 建議進入 Holdout 候選（單軸）  
- [x] **不推薦單獨 holdout**（合併選舉時提供執行 knob）

**主因**：淨期望 -6.48/趟、valid 毛 PnL 深度為負；QSL 改善是真實結構發現，但不足以構成獨立當選 config。

**Grid 內相對最佳（供 leaderboard / 合併選舉）**：

```yaml
relative_best_params:
  ioc_slippage_points: 3
  trail_points: 6
```

**為什麼仍登錄 leaderboard**：valid_score **-16.14** 為四軸中執行面最佳；`trail_points: 6` 與 risk-exit 冠軍一致，Phase 4 合併時應 **鎖定一處** 由 risk-exit 主導、execution 僅保留 `ioc_slippage_points`。

### 協作備註（含 Phase 1 後 compare_fill_audits）

- 已撰寫 `peer_review_agent-conservative.md`；接受 conservative 對「進場濾網無法拉正淨期望」的結論，本軸補強 QSL 但非聖杯。
- `trail_points` 與 `agent-risk-exit` 重疊 — 合併 config 時避免雙重優化。
- Phase 1 Pass 後：`compare_fill_audits` 驗證 IOC tier vs 券商實際 fill。

### 免責與人類決策權

- 本分析 **不** 構成 Pilot / Live Ready。  
- Holdout（2026-05）：Phase 4 前填「未跑」。  
- Overfitting 自評摘要：**medium** — QSL 改善穩健但淨期望全負。

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [x] 已確認與 SHARED_ASSUMPTIONS v1.1 及 PLAN 一致
- [x] 已完成 peer_review（`peer_review_agent-conservative.md`）
- [x] 已回覆 peer_review 質疑（若有）

**回覆摘要**：conservative 質疑「窄 band 是否必要」— 本軸同意瓶頸在出場/trail；執行面已驗證 trail=6。見 `peer_review_agent-conservative.md` §4。
