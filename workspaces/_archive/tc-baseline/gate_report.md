# FT-005 Gate Report — tc-baseline（Phase 0）

> **狀態：MVPClosed / No-Go at Phase 0（2026-06-28）** — `timeout_tick` counterfactual 未過預檢門檻；**未**實作 plugin / baseline 回測。見 [`SPEC §8`](../../docs/features/timeout-continuation/SPEC.md)。

**Thesis**：timeout-selective entry（武裝後等 `momentum_timeout` 再進場）  
**Valid 區間**：2026-04-01 ～ 2026-04-30  
**輸入 log**：v1 `agent-conservative` baseline（回踩 hybrid）  
**產物**：[`reports/counterfactual_timeout_entry.json`](reports/counterfactual_timeout_entry.json)

> 門檻定義：[`docs/features/timeout-continuation/SPEC.md`](../../docs/features/timeout-continuation/SPEC.md) §6 Phase 0 預檢

---

## Phase 0 預檢（timeout cohort · `timeout_tick` 進場）

| 指標 | 門檻 | 值 | Pass |
|------|------|-----|------|
| gross expectancy/趟 | **> 5** | **4.10** | ☐ |
| net expectancy/趟 | **> 0** | **-0.90** | ☐ |
| episode_count（timeout） | — | 83 | |

**結論**：**No-Go** — 不開 `strategy-timeout-continuation` plugin；不跑 Phase 2 baseline。

---

## 進場時點敏感度（v1 outcome=timeout 子集，ATR barrier sim）

| 進場時點 | n | gross/趟 | net/趟 | 解讀 |
|----------|---|----------|--------|------|
| **armed_tick** | 83 | **+36.07** | **+31.07** | 事後標 timeout 的脈衝起點仍強（FT-004 一致）；**非** Thesis B 可實盤路徑 |
| **armed+60s** | 83 | +18.42 | +13.42 | 延遲 60s 仍正，但低於 G1 |
| **timeout_tick** | 83 | **+4.10** | **-0.90** | **主假說** — 180s 後進場 ≈ 追價，edge 消失 |
| **armed+120s** | 83 | -3.02 | -8.02 | 惡化 |

**never_near_vwap** 子集（timeout）：`timeout_tick` gross **+5.48**、net **+0.48**（n=57）— 略過 G1、勉強過 G2，但全 timeout cohort 未過預檢。

---

## 與 FT-004 對照

| 項目 | FT-004 Thesis A | FT-005 Thesis B（本輪） |
|------|-----------------|-------------------------|
| 進場 | armed 同 tick 全 cohort | timeout 當 tick（只吃 timeout 子集） |
| 結論 | No-Go（gross +1.89 全 cohort） | **No-Go at Phase 0**（timeout_tick 未過） |
| 診斷 | 全進稀釋；timeout 子集 armed 時點強 | **延遲至 timeout 摧毀 edge**；順勢 alpha 需更早進場，與「等回踩失敗再進」矛盾 |

---

## §Decision

| 欄位 | 值 |
|------|-----|
| 簽核人 | Agent（Phase 0 證據） |
| 日期 | 2026-06-28 |
| 決策 | **No-Go — MVPClosed at Phase 0**（`thesis_b_phase0_no_go`） |
| 備註 | Plugin / baseline **未實作**。保留 counterfactual 工具與 JSON。下一 thesis：mean-reversion 或結構性早進（非 timeout 尾端）。 |
