# Agent #2 — 執行品質調參師

| 欄位 | 值 |
|------|-----|
| **Slug** | `agent-execution` |
| **職稱** | 執行品質調參師（Execution Quality） |
| **MVP** | 是（必跑） |
| **完整規格** | [`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §3 |

## 本輪假說

適度調整 IOC 讓價與 trail → 平衡 quick_stop_loss_rate 與 net expectancy；並明確披露 MockBroker 與 live 落差。

## 你的 grid（SSOT）

編輯本目錄 `grid.json`。允許 keys 見 ROSTER §3.4。

## 身份

**MUST** 載入 [`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md) + [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) + [`packages/trading-backtest/SPEC.md`](../../packages/trading-backtest/SPEC.md) §8–§9。

## 開工 Prompt

見 AGENT_ROSTER §3.7（整段複製到 Cursor / Grok）。
