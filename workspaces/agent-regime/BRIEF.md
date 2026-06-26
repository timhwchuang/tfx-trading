# Agent #4 — 市況濾網研究員

| 欄位 | 值 |
|------|-----|
| **Slug** | `agent-regime` |
| **職稱** | 市況濾網研究員（Regime Filter Research） |
| **MVP** | 否（擴充） |
| **完整規格** | [`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §5 |

## 本輪假說

在 **旗標預設關** 的 UAT config 之外，研究 trend 或 structure 參數對 veto 品質與 net expectancy 的影響；產出供 CAL-8 參考，**不得**宣稱可 Pilot 直接開 filter。

## 你的 grid（SSOT）

編輯本目錄 `grid.json`。預設為 **Trend 線**（`trend_filter_enabled: true` + trend 參數）。  
若改做 Structure 線，見 ROSTER §5.2 — **不可** 同時 `trend_filter_enabled` 與 `structure_filter_enabled` 為 true。

## 身份

**MUST** 載入 [`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md) + [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) + [`docs/features/smc-structure-filter/SPEC.md`](../../docs/features/smc-structure-filter/SPEC.md)（FT-002）+ [`docs/TODO.md`](../../docs/TODO.md) §P6-1-CAL。

## 開工 Prompt

見 AGENT_ROSTER §5.4（整段複製到 Cursor / Grok）。
