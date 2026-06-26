# Agent #3 — 出場與風控調參師

| 欄位 | 值 |
|------|-----|
| **Slug** | `agent-risk-exit` |
| **職稱** | 出場與風控調參師（Risk & Exit Architecture） |
| **MVP** | 否（擴充） |
| **完整規格** | [`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §4 |

## 本輪假說

固定 TP / trail / 連虧上限 的組合決定 **skew**；過緊 trail → 秒停損；過鬆 TP → MDD 放大。目標是在不放大日虧上限的前提下，改善 valid expectancy 與尾部風險結構。

## 你的 grid（SSOT）

編輯本目錄 `grid.json`。允許 keys 見 ROSTER §4.3。

**禁止**：為拉高 PnL 單獨放大 `max_daily_loss_points`；以 `min_atr_threshold` / IOC 為主軸（屬 #1 / #2）。

## 身份

**MUST** 載入 [`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md) + [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)。

## 開工 Prompt

見 AGENT_ROSTER §4.5（整段複製到 Cursor / Grok）。
