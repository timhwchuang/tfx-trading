# UAT Checklist (kernel / consuming app integration)

Use when integrating `trading-engine@v0.2.2` for simulation → paper → small live.

**App deployment** (Windows env, tick archive, reporting): complete [`APP.md`](APP.md) **Phases 0–2** (through first stable simulation week) **before** kernel Phase B below.

Prerequisites: [trading-engine README § Go-Live](../../packages/trading-engine/README.md), [docs/ops/LIVE_SAFETY.md](../ops/LIVE_SAFETY.md), [trading-engine SPEC §4.2](../../packages/trading-engine/SPEC.md).

---

## Phase A — Repo & config

| # | Item | Pass | Notes / date |
|---|------|:----:|--------------|
| A1 | App pins `trading-engine@v0.2.2` (git tag) | ☐ | |
| A2 | `.env` from `.env.example`; **not** in git | ☐ | |
| A3 | `python run_tests.py` green in trading-engine package | ☐ | ~112 tests |
| A4 | App boots with `ShioajiLiveBootstrap` + injected ports | ☐ | |

---

## Phase B — Simulation (full session)

| # | Scenario | Pass | Expected | Notes / date |
|---|----------|:----:|----------|--------------|
| B1 | Full trading day tick flow | ☐ | Entry/exit signals, fills, `position_qty` correct | |
| B2 | `session_force_flatten_time` with open position | ☐ | Kernel arms exit; position flat after fill | |
| B3 | Disconnect → reconnect (`event_code` 12/13) | ☐ | `_on_reconnected`: reconcile → sync → resubscribe; **`_api_connected` only if subscribe + session-healthy ATR**; else session watchdog relogin | |
| B4 | Pending timeout (short `pending_timeout_sec` in test cfg) | ☐ | CRITICAL alert; `block_new_entry`; sync runs | |
| B5 | Invalid strategy signal (test `qty=0`) | ☐ | Warning log; **no** arm | |
| B6 | `get_state_snapshot()` matches broker after sync | ☐ | `snap.position_qty` / `dir` consistent | |
| B7 | Order callback routing (Shioaji `OrderState`) | ☐ | `python -m live.order_smoke` → `委託回報` + `FILL_AUDIT`; no spurious pending timeout | See [`LIVE_SAFETY.md`](../ops/LIVE_SAFETY.md) |

---

## Phase C — Paper trade (≥3 sessions)

> **範圍說明**：≥3 sessions 是**狀態機與 audit 產出**的最低驗證，**不是** Pilot 量化門檻。Expectancy / Sharpe / MDD、樣本 20 日、人類簽核等**全部在** [`APP.md`](APP.md) **Phase 5**。Kernel UAT Pass ≠ Pilot Ready。

| # | Item | Pass | Notes / date |
|---|------|:----:|--------------|
| C1 | `SIGNAL_AUDIT` / `FILL_AUDIT` logged every trade | ☐ | |
| C2 | `DAILY_SUMMARY` at day reset | ☐ | |
| C3 | `AlertPort` received test CRITICAL (manual inject OK) | ☐ | |
| C4 | No direct mutation of `engine.*` state in app/telemetry | ☐ | Code review |
| C5 | No manual orders on same contract as kernel | ☐ | |
| C6 | ATR refresh failures only warn; strategy still safe | ☐ | See LIVE_SAFETY |

---

## Phase D — Small live (1 lot, monitored)

| # | Item | Pass | Notes / date |
|---|------|:----:|--------------|
| D1 | Go-Live Checklist (README) all checked | ☐ | |
| D2 | Capital limit documented (max loss acceptable) | ☐ | |
| D3 | On-call / alert channel active during session | ☐ | |
| D4 | End-of-day: kernel flat or documented exception | ☐ | |
| D5 | Post-mortem log archive (ticks, audits, alerts) | ☐ | |

---

## Phase E — Sign-off

| Field | Value |
|-------|-------|
| App / strategy repo | |
| trading-engine tag | v0.2.2 |
| UAT owner | |
| Simulation completed | |
| Paper sessions (count) | |
| Live sessions (count) | |
| Issues found | |
| **UAT result** | ☐ Pass → continue &nbsp; ☐ Fail → fix before live |

---

## Quick reference: log lines to watch

```
SIGNAL_AUDIT
FILL_AUDIT
DAILY_SUMMARY
ALERT [CRITICAL]
拒絕 OrderSignal
Pending 超時
Session 看門狗
No-tick 看門狗
持倉對帳
```

## Regression（Pilot 前持續）

Phase B3–B6（斷線重連、pending 超時、invalid signal、`get_state_snapshot` 對帳）應在以下時機**重跑並更新簽名表**（自動化：`cd packages/trading-engine && python run_tests.py`，含 `test_kernel_uat_regression.py`）：
- `trading-engine` tag 升級
- app 重連 / 暖機 / `sync_positions` 邏輯變更
- [`APP.md`](APP.md) Phase 6 切 CA 前（若 Phase 4 後有程式變更）

重連後 **sync_positions → 首 tick 暖機 → 倉位與券商一致** 是 Pilot 前最該信任的機制；證據併入 `uat_evidence/`。

## After UAT

Record outcomes in your app repo (wiki / issue). Open kernel issues only for **reproducible** bugs with test or log evidence.
