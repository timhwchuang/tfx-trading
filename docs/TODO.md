# trading-app — Roadmap

> **執行環境：Windows**。原則：**UAT 驗狀態機與對帳，不驗獲利**。
> 文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。Monorepo：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading)。

## 目前狀態（2026-06-17）

| 階段 | 狀態 |
| ---- | ---- |
| Phase 0～2 狀態機 / 訊號 / 委託 | ✅ 已落地（kernel + plugin） |
| **Phase 3 UAT** | **可開跑** — 待永豐模擬 API 金鑰 → [`uat/APP.md`](uat/APP.md) |
| Phase 4 運維骨架 | ✅ P4-1～12 已落地；Pilot 前 Telegram / 斷網實機驗收 |
| Phase 5 Pilot | 見 [`uat/APP.md`](uat/APP.md) Phase 5（量化 gate：Expectancy/Sharpe/MDD + 穩定性） |
| Phase 6 策略真實化 | 骨架 ✅（旗標預設關）；**B 類 tooling ✅**（待 UAT tick 跑 CAL-8）；P6-4/5 待做 |
| Phase 7 策略介面 | ✅ `trading-engine` Protocol + `strategy-vwap-momentum` plugin |
| Phase 8 / monorepo | ✅ `tfx-trading`；`trading_app_engine_ports()` 接線 |

> **UAT Ready ≠ Live Ready**。Phase 6 是 Live gate，不是 UAT gate。

**測試基線**：`bash scripts/run-all-tests.sh`（monorepo 根）— app **81**、engine **80**、strategy **33**（backtest 各自）。

---

## Open items（未完成）

### Blocker — 人類

- [ ] 申請永豐**模擬** API（行情 + 帳務 + 交易；UAT 不需 CA）
- [ ] 依 [`uat/APP.md`](uat/APP.md) 跑第一段模擬

### P2-1 多口 / 部分成交

- [ ] 完整 qty>1 倉位管理（防禦層已有；Pilot 暫假設 **qty=1**）
-  owner: `trading-engine`

### P6-1-CAL（Live gate — 待 UAT tick）

> **前提**：`trend_filter_enabled` 預設 **false**；`trend_min_strength=0.0` 是最嚴格（最多 veto）。開啟前必過 **CAL-8** 人類簽核。
> **語意 / CLI**：[`packages/strategies/vwap-momentum/SPEC.md`](../packages/strategies/vwap-momentum/SPEC.md) §6.1 · sweep 接線 [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts

**A 類（合成，已完成）**

- [x] CAL-1～5：時間切片、trend harness、sweep `trend_*` 參數、`test_trend.py` / `test_trend_calibration.py`

**B 類（真實 UAT 資料，進行中）**

- [x] Tooling：`forward_pnl.py`、`calibration_cli`、`param_sweep(forward_policy=...)`
- [ ] **1. 累積**：UAT 連續 **≥5 交易日**；`TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1`；log 含 `reason=trend_veto`
- [ ] **2. Harness**：`cd apps/trading-app/src` → `python -m reporting.calibration_cli <log> --dates ... --cache-dir tick_cache --forward-seconds 1800`
- [ ] **3. Sweep**：同上 + `--sweep --sweep-output sweep_result.jsonl`（grid 見 SPEC §6.1）
- [ ] **4. CAL-8 Go/No-Go**：人類簽核 → 寫入 [`WeeklyStatus.md`](WeeklyStatus.md)；**No-Go** 則維持 `trend_filter_enabled=false`

- owner: `strategy-vwap-momentum` + `trading-app/reporting` + `trading-app/sweep`

### P6-4 Position sizing

- [ ] 依賴 P2-1；`risk_pct` / `max_contracts` 上線前須人類 Go/No-Go

### P6-5 追價進場

- [ ] Live gate 後段；非 UAT blocker

### P4-13 Live 連線護欄（斷線 / 恢復 — Pilot 前）

> **決策（2026-06-17）**：恢復後須等指標窗口重新對齊才允許新進場；單日斷線過多應停玩並排查網路；有倉斷線必須告警。
> 見 [`WeeklyStatus.md`](WeeklyStatus.md) 2026-06-17 備註；實作後更新 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) + UAT checklist。

- [x] **P4-13-A 恢復暖機（reconnect warmup）**：`_on_reconnected` / 重訂閱成功後設 `reconnect_warmup_until_ts`（預設 300s），暖機期間 `RiskGate` 擋 **entry**、仍允許 **exit** / force-flatten
- [x] **P4-13-B 單日斷線上限**：`api_connected=False` 事件計數（預設 **3 次/交易日**），達標 → `block_new_entry=True` 至日切換 + `AlertPort` **CRITICAL**
- [x] **P4-13-C 有倉斷線告警**：`_mark_disconnected` 時若 `position_qty>0` → `AlertPort` **CRITICAL**
- [x] **P4-13-D config**：`config.yaml` `operations` + engine `Settings`（`reconnect_warmup_sec`、`max_disconnects_per_day`、`alert_on_disconnect_with_position`、`atr_stale_multiplier`）
- [x] **P4-13-E 測試**：`trading-engine/tests/runtime/test_atr_stale_and_reconnect_guards.py` + strategy `test_evaluate_pure`
- [ ] **P4-13-F UAT**：[`uat/APP.md`](uat/APP.md) 增「手動斷網 30–60s → 恢復 → 確認無意外 entry / 有倉有告警 / 三次斷線停玩」
- owner: `trading-engine`（護欄邏輯）+ `trading-app`（config、AlertPort、UAT 條目）
- gate: **Pilot 前**必過；[`uat/APP.md`](uat/APP.md) Phase 4 可先行驗 reconnect / 暖機 / 斷線上限（實作後）

### Phase 8 後續（非 UAT blocker）

- [ ] NDJSON 事件 sink（第一段乾淨 UAT 後）
- [ ] `session.sync_positions` Action 字串化統一

---

## Gates（摘要）

| Gate | 條件 | 文件 |
| ---- | ---- | ---- |
| **Merge code** | `run_tests.py` 全綠 | 各 repo |
| **UAT** | 模擬 API + `simulation: true` + checklist Pass | [`uat/APP.md`](uat/APP.md) + [`uat/KERNEL.md`](uat/KERNEL.md) |
| **Pilot** | UAT 連續零異常 + CA + 秒停損率達標 | [`uat/APP.md`](uat/APP.md) Phase 5 |
| **Live** | §P6-1-CAL 通過（CAL-8）+ 人類簽核 | 本檔 §P6-1-CAL、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) |

---

## 文件索引（勿重複維護）

| 需要… | 讀… |
| ----- | --- |
| 跑 UAT | `uat/APP.md` |
| Kernel scenario | [`uat/KERNEL.md`](uat/KERNEL.md) |
| 週報 / 人類 follow-up | [`WeeklyStatus.md`](WeeklyStatus.md) |
| Windows 運維 | [`ops/WindowsOps.md`](ops/WindowsOps.md) |
| 架構邊界 | 根 [`SPEC.md`](../SPEC.md) §7 |
| 回測 / sweep 規格 | [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts |
| P6-1 trend 校準（Live gate） | 本檔 §P6-1-CAL + vwap [`SPEC.md` §6.1](../packages/strategies/vwap-momentum/SPEC.md) |
| AI 協作規範 | [`AGENTS.md`](AGENTS.md) |