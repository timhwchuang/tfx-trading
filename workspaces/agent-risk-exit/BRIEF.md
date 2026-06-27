# Agent #3 — 出場與風控調參師

| 欄位 | 值 |
|------|-----|
| **Slug** | `agent-risk-exit` |
| **職稱** | 出場與風控調參師（Risk & Exit Architecture） |
| **MVP** | 否（擴充） |
| **完整規格** | [`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §4 |

## 本輪假說

**Round 1**（已完成／可棄用）：固定 TP / trail / 連虧 — 未含 `hard_stop`，與 Phase 3.6 診斷不符。grid 備份：`grid.round1.json`。

**Round 2**（待人類批准）：[`round2_proposal.md`](../round2_proposal.md) — **只 tune 出場尺度**（`hard_stop_points` + `trail_points` + `fixed_tp_points`）；進場／執行已鎖定於 `config/config.yaml`。

## 你的 grid（SSOT）

- Round 1：`grid.round1.json`（歷史）
- **Round 2 批准後**：`Copy-Item grid.round2.json grid.json` 再 sweep

允許 keys 見 ROSTER §4.3（含 Round 2 的 `hard_stop_points`）。

**禁止**：為拉高 PnL 單獨放大 `max_daily_loss_points`；以 `min_atr_threshold` / IOC 為主軸（屬 #1 / #2）。

## 身份

**MUST** 載入 [`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md) + [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)。

## 開工 Prompt

見 AGENT_ROSTER §4.5（整段複製到 Cursor / Grok）。
