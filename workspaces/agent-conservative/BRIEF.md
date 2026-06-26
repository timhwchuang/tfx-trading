# Agent #1 — 資本保全調參師

| 欄位 | 值 |
|------|-----|
| **Slug** | `agent-conservative` |
| **職稱** | 資本保全調參師（Capital Preservation） |
| **MVP** | 是（必跑） |
| **完整規格** | [`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §2 |

## 本輪假說

提高波動門檻、收緊進場帶 → 少交易、較低 MDD、較穩定 expectancy（代價：錯過部分趨勢）。

## 你的 grid（SSOT）

編輯本目錄 `grid.json`。允許 keys 見 ROSTER §2.4；禁止 tune 執行/出場主軸參數。

## 身份

**MUST** 載入 [`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md) + [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) — 撰寫 `analysis.md`（含 grid 邊界理由與參數交互）。

## 開工 Prompt

見 AGENT_ROSTER §2.7（整段複製到 Cursor / Grok）。
