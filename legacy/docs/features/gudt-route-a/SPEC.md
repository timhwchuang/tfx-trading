---
id: FT-021
slug: gudt-route-a
status: UAT
opened: 2026-06-30
owner: human+agent
target: UAT
audit_schema_version: 1
---

# FT-021 — GUDT Route A UAT Stack

**功能票據**（範圍、DoD、parity 數字）。策略怎麼運作、參數表、指令 → **[`packages/strategies/gudt-route-a/README.md`](../../../packages/strategies/gudt-route-a/README.md)**。

---

## 1. 在做什麼

把 FT-018b 研究層的 **Route A 多單 + 可選翻空** 做成 `gudt_route_a` plugin，在 **同一顆 TradingEngine** 上回測與模擬下單。

**不取代** B′ 封板研究（[`SEAL_FT018b_B_PRIME.md`](../../../workspaces/gudt-baseline/SEAL_FT018b_B_PRIME.md)）。

---

## 2. 里程碑

| 日期 | 狀態 |
|------|------|
| 2026-06-30 | Draft · plugin + parity harness |
| 2026-07-01 | 決策/執行 parity 全綠 · 文件重整 |
| **2026-07-02** | **模擬 UAT 開跑**（`gudt-route-a-baseline` config） |

---

## 3. Parity（驗收數字）

區間 **2025-05-01 .. 2026-06-30**，br5 router，stack = Route A + EMA5 + structural confirm。

研究 CF 對照：[`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)

| 指標 | CF 基準 | 腳本 |
|------|---------|------|
| Full net | **+1781** | `ft021_parity_check` |
| flip_days | **2** | 同上 |
| extend_days | **4** | 同上 |
| 執行 n | CF plan = kernel fills | `ft021_execution_parity` |

執行層 net 差異 **warn-only**（不擋 Pass）。

---

## 4. Definition of Done

- [x] `strategy-gudt-route-a` + `load_named_strategy("gudt_route_a")`
- [x] `workspaces/gudt-route-a-baseline/` + `ft021_run_baseline` / `ft021_execution_parity`
- [x] 決策 parity + 執行 parity（UAT_2m / H1 / spot）
- [x] Package README（策略條件白話版）
- [ ] **UAT 模擬盤**（2026-07-02 起）— 人類每日對帳
- [ ] Bugbot 無未解 Critical/High

實作計畫：[`PLAN.md`](PLAN.md)

---

## 5. 相關路徑

| 路徑 | 用途 |
|------|------|
| [`packages/strategies/gudt-route-a/README.md`](../../../packages/strategies/gudt-route-a/README.md) | 策略說明（**先看**） |
| [`packages/strategies/gudt-route-a/SPEC.md`](../../../packages/strategies/gudt-route-a/SPEC.md) | Package 契約 |
| [`workspaces/gudt-route-a-baseline/README.md`](../../../workspaces/gudt-route-a-baseline/README.md) | 回測 / parity 指令 |
| [`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md) | 研究回測表 |
