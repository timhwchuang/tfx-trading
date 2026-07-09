---
id: FT-023
slug: gudt-wash-beta
status: UAT
opened: 2026-07-01
owner: human+agent
target: UAT
---

# FT-023 — GUDT Wash Beta

Wash 日 **open long → session force flatten** 的獨立 plugin（不覆蓋 FT-021 Route A）。

策略細節 → [`packages/strategies/gudt-route-a/README.md`](../../../packages/strategies/gudt-route-a/README.md)（Wash Beta 章節）。

## Oracle 聲明

回測/UAT 使用 wash probe CSV 的 **oracle wash gate**（與 FT-021 相同）。策略不在盤中即時判斷是否 wash 日。

- 進場：08:45 首筆可用 tick（或 `open_0845`）
- 出場：`session.force_flatten_time`（預設 13:44）**市價 tick**
- 禁止 structural stop / flip / B′ 路由

## Parity

| 指標 | 要求 |
|------|------|
| Execution `n` | CF rounds == kernel fills（硬門檻） |
| Net Δ | warn-only |
| UAT slice | **2026 H1** `2026-01-01 .. 2026-06-30` |

CF 研究 ledger：[`WASH_BETA_LEDGER.md`](../../../workspaces/gudt-baseline/WASH_BETA_LEDGER.md)

## Definition of Done

- [x] `gudt_wash_beta` plugin + workspace
- [x] `ft023_*` parity harness
- [x] H1 2026 execution parity PASS (`n=44/44`, 2026-07-02)
- [ ] Bugbot ≤3 rounds

## Kernel open entry

`GudtWashBetaStrategy` arms **market** buy on `long_entry` (not limit IOC) so 08:45 open chase days fill; CF still uses first-tick market price. `ioc_slippage_points: 12` applies to exit IOC only.
