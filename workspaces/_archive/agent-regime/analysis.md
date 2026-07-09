# Analysis — agent-regime（市況濾網研究員）

**Agent**：agent-regime  
**Role**：市況濾網研究員  
**分析日期**：2026-06-27  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04（Holdout 2026-05 封印）  
**Regime 線**：Trend（與 `grid.json` 一致；Structure 未啟用）  
**Sweep 執行模型**：`ft003_run_sweep.py`（bulk，`run_id` c38f9769db37）  
**分析撰寫模型**：Cursor Agent（senior-trading-professional 視角）

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §5  
> **FT-002**：[`docs/features/smc-structure-filter/SPEC.md`](../../docs/features/smc-structure-filter/SPEC.md)

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：在 **研究 overlay** 下評估 trend filter 參數對進場品質的影響；產出 CAL-8 前置的 veto 敘事，**不**建議 Pilot 直接開 filter。

**本次調參假說**：適度 `trend_min_strength`（0.2–0.4）可 veto 弱趨勢假突破，提升 valid expectancy；`trend_slope_min` 微調可過濾橫盤。

**Regime 線與 grid 邊界理由**（CAL-8 前置；filter 預設關、研究 overlay）：

- **Trend 線**（`structure_filter_enabled` 未開，互斥合規）。
- `trend_filter_enabled: [true]`：強制 overlay 研究；UAT/live 預設仍 false。
- `trend_min_strength` 0.2 / 0.4 / 0.6：對照 SPEC §6.1 校準區間；0.6 測最嚴門檻。
- `trend_slope_min` 0.0 / 0.05：測斜率輔助門檻；與 EMA period 交互（未 tune）。

**預期參數交互**（≥2 組）：

- `trend_min_strength` ↑ × `trend_slope_min` ↑ → veto_rate ↑、trade_count ↓（預期）。
- `trend_min_strength` ↑ × 低波動月 → 可能 **零 veto**（回測 harness 未記錄真實 forward policy）。

**預期 Trade-off**：減少劣質進場 vs 錯過趨勢初段；**須 CAL-2/5/7 forward replay** 才能評 veto 品質。

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | -21.99 | filter **關**（UAT 預設） |
| daily_pnl_points | -48.0 | |
| trade_count | 150 | |
| day_count | 20 | |

**交易員一句話評論**：filter 關基線；作為 trend overlay 研究對照。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | veto 相關 | vs Baseline |
|------|-------------|--------|-----------|-------------|
| 1 | -21.32 | `{'trend_filter_enabled': True, 'trend_min_strength': 0.2, 'trend_slope_min': 0.0}` | veto_rate=0.00% | **+0.67** |
| 2 | -21.32 | `{'trend_filter_enabled': True, 'trend_min_strength': 0.2, 'trend_slope_min': 0.05}` | veto_rate=0.00% | **+0.67** |
| 3 | -21.32 | `{'trend_filter_enabled': True, 'trend_min_strength': 0.4, 'trend_slope_min': 0.0}` | veto_rate=0.00% | **+0.67** |

**最差 1 組**：`{'trend_filter_enabled': True, 'trend_min_strength': 0.6, 'trend_slope_min': 0.0}` — valid_score **-21.58**。

**參數敏感度**：

- **trend_min_strength / trend_slope_min**：六組中 **五組 valid KPI 完全相同**（151 筆、毛 -14.5）；僅 strength=0.6 略差（152 筆、-21.58）。grid **幾乎無辨識力**。
- **veto_rate**：全組 **0%**（`veto_metrics` 標 SYNTHETIC GUARD）— 回測未產生真實 trend_veto 統計，**不得**用於 Go/No-Go。
- **結論**：本輪 sweep 僅證明「在此 overlay 下 KPI 與 baseline 幾乎無差」，**非** filter 可上線的證據。

**最有價值的一個發現**：Trend overlay 在現有 backtest 路徑 **未觸發有效 veto**；要評估 regime 必須走 **UAT replay + calibration_cli**（TODO §P6-1-CAL），本 sweep **不能**支持開 filter。

## 4. Overfitting 與穩健性評估

**Train vs Valid**（代表組 `trend_min_strength: 0.2`, `trend_slope_min: 0.0`）：

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| daily_pnl_points | -474.0 | -14.5 | valid 毛損遠小於 train | 差異主因 **filter overlay 改變交易路徑**，非典型 overfit |
| trade_count | 302 | 151 | 約半 | 樣本仍 ≥20 |
| quick_stop_loss_rate | 29.1% | 32.5% | valid 略差 | QSL 未因 filter 改善 |
| expectancy_net | -6.57/趟 | -5.10/趟 | valid 略好 | 仍為負；改善幅度 <0.7 vs baseline |

**Overfitting 風險**：**低**（grid 無有效區分） / **資訊風險：高**（veto 指標不可信）

**理由**：

1. 六組結果高度同質，不存在「挑最佳 combo」的 overfit 誘因。
2. `veto_metrics` 為合成占位，任何「valid 略優 +0.67」**不具決策意義**。

**Holdout 風險因子**：

- 5 月若開 filter 無 UAT 校準，veto 品質未知。
- 與 risk-exit 出場改善疊加時，filter 可能進一步壓縮樣本至統計不足。

**整體穩健性**：**不建議**將本 grid 結果納入 holdout 合併 config；維持 `trend_filter_enabled: false` 直至 CAL-8。

---

## 5. 推薦與下一步

- [ ] 建議進入 Holdout 候選（**研究用**）  
- [x] **不推薦**（含不建議開 filter）

**主因**：veto_rate=0、grid 無辨識力、CAL-8 未過；valid +0.67 在統計與實務上 **無意義**。

**研究記錄（非 recommended_params）**：

```yaml
# 僅文檔化 grid 冠軍；不得寫入 elected_config
research_overlay_params:
  trend_filter_enabled: true
  trend_min_strength: 0.2
  trend_slope_min: 0.0
```

**為什麼不推薦開 filter**：回測路徑未產生可信 veto 統計；QSL 未改善；須 ≥5 日 UAT + `calibration_cli` 後再議（TODO §P6-1-CAL）。

### 協作備註（CAL-8、P6-1-CAL）

- 已撰寫 `peer_review_agent-risk-exit.md`；同意出場軸為 holdout 主候選，regime 本輪退出合併。
- Phase 3.6 `ft003_volatility_baseline.py` 完成後，可再評估是否申請 **第二輪** structure/trend grid（須人類批准 SPEC §4.4）。

### 免責與人類決策權

- 不構成 Pilot / Live Ready。Holdout：未跑。UAT 預設 filter 仍關。
- Overfitting 自評摘要：**low**（無有效 tune）/ **decision value: none**

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [x] 已確認與 SHARED_ASSUMPTIONS v1.1 及 PLAN 一致
- [x] 已完成 peer_review（`peer_review_agent-risk-exit.md`）
- [x] 已回覆 peer_review 質疑（若有）

**回覆摘要**：risk-exit 建議勿在合併 config 開 filter — 同意。
