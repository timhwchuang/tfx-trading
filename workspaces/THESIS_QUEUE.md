# Thesis Queue — Alpha 提案佇列

> **用法**：Agent **可**填 `draft-proposal`；人類 **Pick 一個**改 `human-approved` 後才准 Phase 0 CF。  
> Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../docs/features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)

**狀態**：`draft-proposal` → `human-approved` → `in-cf` → `mvpclosed` | `holdout-pending` | `landed`  
**Rejected** 列保留原因，避免重提案。

---

## 佇列總覽

| ID | 工作標題 | 狀態 | 本質差異（一句） | 下一步 |
|----|----------|------|------------------|--------|
| P-001 | Regime VWAP stretch fade | `draft-proposal` | 非 FT-006：加 **regime 門檻**（波動分位 + 時段），降頻拉高 gross | 等人類 Pick |
| P-002 | Midday liquidity pause fade | `draft-proposal` | 非 ORB/SCB：針對 **11:00–12:30** 低波動區間假突破 fade | 等人類 Pick |
| P-003 | Opening gap inventory fade | `draft-proposal` | 非 FT-009：做 **開盤 gap vs 前收** 過度反應，非 opening range breakout | 等人類 Pick |

---

## P-001 — Regime VWAP stretch fade

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28

**故事**：FT-006 證明「無條件 stretch fade」valid 可過但 holdout 掛。假設 edge 只存在 **低波動 regime**（當日 1m realized vol 分位 < p30）且 **早盤**（09:00–10:30），過度延伸後做市商/短線資金會拉回 VWAP。

**不是 FT-006 因為**：進場要同時滿足 regime 標籤 + 時段 + stretch 門檻；預期 n 降、單筆 gross 目標 > 8。

**粗算**：train n 估 40–80；gross 目標 6–10/趟。

**主要風險**：regime 標籤事後選切 → pre-register 分位計算方式（僅用當日已走資料）。

**Falsify**：2025 train G2 未過 → MVPClosed。

---

## P-002 — Midday liquidity pause fade

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28

**故事**：11:00–12:30 常出現低成交量、假突破後快速回歸。進場：1m 收盤突破近 30 分鐘區間且 **vol_1s 低於** 早盤 p50 → fade 回區間中軸。

**不是 ORB/SCB 因為**：不用開盤 range；時段與 **流動性枯竭** 為核心，非 trend confluence。

**粗算**：n 估 50–100；gross 目標 5–8/趟。

**主要風險**：與 hybrid「vol 門檻」語意相近 → CF 必須證明瓶頸不是 vol-only 恆真（見 diagnosis §6.3）。

**Falsify**：funnel 顯示 vol 非瓶頸但 net 仍負 → 放棄或改 thesis。

---

## P-003 — Opening gap inventory fade

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28

**故事**：開盤相對前日收盤 gap > k×ATR 時，短線 inventory 調整導致前 30–60 分鐘 partial fill back toward prior close / VWAP。

**不是 FT-009 因為**：不做 range breakout；觸發是 **gap 大小**，出場是 gap fill 比例而非 OR 邊界。

**粗算**：n 估 30–60（視 k）；gross 目標 6+/趟。

**主要風險**：gap 事件與 2025 牛熊 regime 強相關 → 須 §3.1 單邊檢查。

**Falsify**：2025 train 單邊 >80% gross → disqualify。

---

## 已決議（範本）

| ID | 決策 | 日期 | 原因 |
|----|------|------|------|
| — | — | — | — |

---

## 人類操作

1. 回覆 Agent 或在本檔改狀態：`P-00x` → `human-approved` 或 `rejected`（附一行原因）
2. 批准後：「依 Playbook 開 FT-012 `<slug>` Phase 0」
