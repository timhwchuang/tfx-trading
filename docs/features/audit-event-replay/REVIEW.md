---
id: FT-001
slug: audit-event-replay
doc_type: review
reviewer: senior-trading-professional
reviewed: 2026-06-17
status: accepted-with-amendments
---

# FT-001 — 資深交易人員審閱（REVIEW）

> **視角**：資深 TXF 交易人員 + Daily Reviewer 協作需求。  
> **結論**：SPEC 方向正確；以下補強已納入 [`SPEC.md`](SPEC.md) §5.5、§6.4、§8 與 [`PLAN.md`](PLAN.md) Phase 3–4。  
> **不納入 FT-001**：高壓模式自動切換、Feature Toggle 實作 → 見 §4 後續 ft 建議。

## 1. 關鍵分析

FT-001 解決的是 **決策時間軸無法完整重建**——目前最痛的三段是：動量啟動（只有 log）、pullback 漏斗（只有日彙總）、風控拒絕（靜默）。`episode_id` + `signal_id` 讓「這筆虧損屬於哪次 episode、哪個執行環節」可追溯，是 Pilot 歸因與 CAL-8 的前置條件。

`DECISION_AUDIT` 與 `SIGNAL_AUDIT` 分層合理：strategy「想什麼」與 kernel「送什麼單」分開，之後加 AI 解釋欄位不會污染執行契約。

## 2. 風險評估（審閱缺口）

| 缺口 | 交易影響 | 處置 |
|------|----------|------|
| 連續 veto / timeout / 無進場 | 高壓日「一直 arm 不到」難一眼看出 | **納入 FT-001**：`DAILY_SUMMARY.pressure` + 可選 streak 欄位 |
| 高壓自動停新進場 | 需人類簽核，非 audit 本身 | **FT-002+**，FT-001 只量測 |
| Feature Toggle 關 audit | determinism / UAT 證據鏈風險 | **FT-002**，SPEC 僅預留 `emit_policy` |
| Agent 無正式消費介面 | timeline 建好卻無交接格式 | **納入 FT-001**：SPEC §8 Agent consumers |

## 3. 建議行動（已併入 SPEC / PLAN）

### 3.1 壓力指標 — `DAILY_SUMMARY.pressure`（Phase 3）

日終必看欄位（SHOULD）：

| 欄位 | 語意 | Daily Reviewer 用途 |
|------|------|---------------------|
| `max_consecutive_veto` | 當日最長連續 trend_veto | 濾網是否過嚴 / regime 不對 |
| `max_consecutive_timeout` | 當日最長連續 momentum_timeout | band 太緊或市況太快 |
| `max_episodes_without_entry` | 連續 armed 但無 entry 最長段 | 策略是否「空轉」 |
| `armed_to_entered_ratio` | entered / armed | 漏斗健康度 |
| `risk_blocked_count` | 當日 risk_blocked 事件數（節流後） | 風控是否擋掉大半交易日 |

**警戒線（交易視角，非 UAT pass）**——供 `uat_report` hints：

- `max_consecutive_timeout >= 5` → 檢查 `entry_band` / `exhaustion_vol` / 當日 regime
- `armed_to_entered_ratio < 0.10` 且 `armed >= 10` → 漏斗異常
- `max_consecutive_veto >= 3` 且 trend filter 已開 → CAL-8 複查

### 3.2 DECISION_AUDIT 可選壓力上下文（Phase 3–4，SHOULD）

在 `momentum_timeout`、`trend_veto`、`risk_blocked` 事件上加 **optional**：

- `consecutive_veto_streak`
- `consecutive_timeout_streak`
- `episodes_since_last_entry`

不進 Phase 1 hot path；由 `DailyObservability` 在 emit 時填入。

### 3.3 `emit_policy` 預留（Phase 4 文件のみ）

事件目錄 MAY 含：

```json
"emit_policy": "required"
```

值：`required` | `optional` | `toggleable`（**toggleable 實作屬 FT-002**）。

### 3.4 Agent 消費者（Phase 3）

見 SPEC §8.1。`build_episode_timeline()` 輸出為各 Agent 的**交接格式**。

## 4. 高壓情境回放範例（§6.4）

連續 3 episode timeout + 1 veto 後才進場——見 SPEC §6.4。  
**交易解讀**：上午橫盤 arm 多、進場少；若無 `pressure` 彙總，Daily Reviewer 只能手掃 log。

## 5. 協作備註

| 角色 | FT-001 完成後 |
|------|----------------|
| **Daily Reviewer** | `python -m reporting <log> --episodes` + `DAILY_SUMMARY.pressure`；異常寫 WeeklyStatus |
| **Senior Trading Professional** | 單 episode timeline + Phase 5 KPI；高壓日先看 `pressure` 再談調參 |
| **工程 Agent** | 照 PLAN Phase 1→4；不自行開高壓自動模式 |
| **Ops** | `pressure` 異常 ≠ 停機；CRITICAL 仍走既有告警 |

## 6. 後續 ft 建議（不塞進 FT-001）

| ID | Slug | 內容 |
|----|------|------|
| FT-002 | `audit-emit-toggle` | `emit_policy=toggleable` 的 config/env + determinism 例外 |
| FT-003 | `pressure-response-mode` | 高壓門檻觸發 `block_new_entry` 建議（**人類簽核**後才實作） |

AI skills 管理：新 Agent 能力開 `docs/features/FT-00N/` + `.grok/skills/`，`TODO.md` 只留一行連結。

## 7. 審閱結論

| 項目 | 判定 |
|------|------|
| FT-001 整體方向 | **通過** |
| 壓力指標 | **納入** Phase 3（日彙總優先） |
| Feature Toggle | **延後** FT-002，SPEC 預留 |
| Agent 介面 | **納入** SPEC §8.1 |
| 高壓自動切換 | **不做**於 FT-001 |

— 審閱人角色：資深交易人員（senior-trading-professional）。Live 決策權在人類。