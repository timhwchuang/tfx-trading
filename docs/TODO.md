# trading-app — Roadmap

> **執行環境：地雲雙管** — Live 建議 **GCP GCE（asia-east1）** 或 **Windows**；回測/CAL 放 **地端 Linux/macOS**（見 [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md)）。原則：**UAT 驗狀態機與對帳，不驗獲利**。
> 文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。Monorepo：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading)。

## 目前狀態（2026-06-23）

| 階段 | 狀態 |
| ---- | ---- |
| Phase 0～2 狀態機 / 訊號 / 委託 | ✅ 已落地（kernel + plugin） |
| **Phase 3 UAT** | **🟢 GCE Live 就緒** — [`uat/APP.md`](uat/APP.md) Phase 0 ✅；**Phase 1** 首個完整交易日待驗（2026-06-24） |
| **GCE Live 節點** | ✅ 已部署（`e2-medium`，Debian 13，asia-east1，08:30–14:00 排程）；見 [`ops/LinuxOps.md`](ops/LinuxOps.md) §GCE |
| Phase 4 運維骨架 | ✅ P4-1～12 已落地；GCE systemd + cron 已設；**P4-13-F 斷網實機**、Telegram 實機待 UAT 演練 |
| Phase 5 Pilot | 見 [`uat/APP.md`](uat/APP.md) Phase 5（量化 gate + 摩擦對帳 + 壓力情境審閱） |
| Phase 6 策略真實化 | 骨架 ✅（旗標預設關）；**B 類 tooling ✅**（P6-1 + **P6-SMC-CAL** harness/sweep）；待 UAT tick 跑 CAL-8；P6-4/5 待做 |
| **FT-002 SMC（工程）** | Phase 1–4 ✅（`REVIEW.md` PASS）；**Phase 5 Land + CAL-8** 待 ≥5 日 UAT |
| **FT-003 回測調參** | **🟢 Phase 3 完成** — 四位 sweep + analysis + peer_review + leaderboard；Phase 4 holdout 待解封；**Phase 6 長歷史**見 [PLAN Phase 6](features/ai-backtest-tuning/PLAN.md#phase-6--長歷史穩健性驗證post-mvp2022) |
| Phase 7 策略介面 | ✅ `trading-engine` Protocol + `strategy-vwap-momentum` plugin |
| Phase 8 / monorepo | ✅ `tfx-trading`；`trading_app_engine_ports()` 接線 |
| **UAT 證據目錄** | ✅ [`uat_evidence/`](../uat_evidence/) 範本 + `reports/`、`snapshots/` 骨架 |

> **UAT Ready ≠ Live Ready**。Phase 6 **P6-1-CAL** / **P6-SMC-CAL**（trend / structure filter）是 Live gate，不是 UAT gate。

**測試基線**：`bash scripts/run-all-tests.sh` — 以實際 `Ran N tests` 輸出為準（2026-06-18：engine **90**、backtest **27**、strategy **60**、app **136**，合計 **313** 全綠）。

### Phase 編號對照（避免混淆）

| 本檔 Roadmap | [`uat/APP.md`](uat/APP.md) 清單 | 意義 |
|--------------|--------------------------------|------|
| Phase 3 UAT | Phase 0–4 | 模擬累積、壓力測試 |
| Phase 5 Pilot | **Phase 5** | 量化 gate + 人類簽核 |
| Phase 6 策略真實化 | Phase 6（切 CA）+ Live CAL-8 | trend filter 等 |
| Phase 7 策略介面 | Phase 7（Pilot 1 口） | 上 CA 後執行 |

> **Pilot 門檻 SSOT**：[`uat/APP.md`](uat/APP.md) Phase 5。`txf-gates.md` / role 檔僅摘要 + 連結。

---

## UAT 開跑檢查（API 金鑰就緒後）

| # | 項目 | 狀態 | 動作 |
|---|------|------|------|
| 1 | Monorepo + venv | ☐ | `bash scripts/setup-dev.sh`；`run-all-tests.sh` 全綠 |
| 2 | `simulation: true` | ✅ 預設 | `apps/trading-app/config/config.yaml` |
| 3 | 環境變數 | ☐ | `SJ_API_KEY` / `SJ_SEC_KEY`；`TICK_ARCHIVE=1`；`KBARS_ARCHIVE=1`；`LOG_FILE` |
| 4 | 目錄 | ✅ 骨架 | `reports/`、`snapshots/`、`uat_evidence/`（見 [`uat_evidence/README.md`](../uat_evidence/README.md)） |
| 5 | Phase 0 證據 | ☐ | 首次 `python -m live` 10 分鐘 + git commit |
| 6 | Phase 3 摩擦 | ☐ 建議 | `config.yaml` → `friction.enabled: true`（net expectancy 從第 6 交易日追蹤） |
| 7 | 週報 | ☐ | 複製 `weekly_kpi_snapshot.md`；`python -m reporting.uat_evidence_export both reports\day*.json` |

**UAT 期間建議啟用的功能**（已落地、不阻擋上線）：

| 功能 | 路徑 / 指令 | 用途 |
|------|-------------|------|
| Tick 落盤 | `TICK_ARCHIVE=1` → `tick_cache/` | determinism、backtest 重現 |
| K 線落盤 | `KBARS_ARCHIVE=1` | ATR 熱身、CAL-8 B 類 |
| 日報 + KPI | `python -m reporting <log> --json` | gross/net、near-miss、type0_pct |
| 週趨勢 | `python -m reporting reports\day*.json --trend`（monorepo 根 + PYTHONPATH） | Phase 3 gross/net、Sharpe、MDD |
| Determinism | `python -m sweep.determinism_check --date …` | Phase 5 可重現性 |
| 證據 CSV | `python -m reporting.uat_evidence_export both reports\day*.json` | broker 對帳 + tick 分層 |
| Pilot gate | `python -m sweep.pilot_gate_check reports\day*.json` | Phase 5 量化預檢 |
| Tick 壓縮 | `python -m storage`（`storage.compress` alias） | 收盤後維護 |
| 歷史快取補洞 | `python -m backfilldata date YYYY-MM-DD`（`apps/trading-app/src`） | 收盤後補缺 tick/kbar；勿與 live 同時 login |
| 回測重跑 | `python -m backtest --code TMFR1 --dates …`（與 `config.yaml` `product_code` 一致） | UAT tick 驗證 |
| P4-13 護欄 | `config.yaml` `operations.*` | 暖機、斷線上限、有倉 CRITICAL |
| Near-miss 漏斗 | `DAILY_SUMMARY.near_miss` | pullback / timeout 診斷 |
| Trend CAL tooling | `python -m reporting.calibration_cli` | P6-1 Live gate 前校準（預設 filter 關） |
| SMC CAL tooling | `python -m reporting.structure_calibration_cli` | P6-SMC-CAL（預設 `structure_filter_enabled: false`） |

---

## Open items（未完成）

### FT-003 — AI 回測調參（[`PLAN`](features/ai-backtest-tuning/PLAN.md)）

**MVP（2026-01～05，先做）**

- [x] Phase 1：`cache_audit` PASS、`determinism_check` PASS（各 agent）
- [x] Phase 2：MVP 兩位 baseline + `analysis.md` §Baseline
- [x] Phase 3：`ft003_run_sweep.py` + `sweep_result.jsonl` + 五段式 `analysis.md`
- [x] Phase 3.4：雙向 `peer_review_*.md`
- [x] Phase 3.5：`leaderboard.jsonl`
- [ ] **Phase 3.6**：四位 sweep 後 — [`PLAN Phase 3.6`](features/ai-backtest-tuning/PLAN.md#phase-36--市場尺度診斷四位-sweep-完成後) · [`ENTRY_FUNNEL_METRICS.md`](features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)（Methods SSOT）· `ft003_volatility_baseline.py` / `ft003_exit_diagnosis.py` · `ft003_episode_diagnosis.py`（§C，**待實作**）· `strategy_diagnosis.md`
- [ ] Phase 4：holdout 解封 + `election_report.md` + `judge_opinion.md`（須引用 `strategy_diagnosis.md`）

**Post-MVP — Phase 6 長歷史（2022+，MVP holdout Gate 後）**

> SSOT：[PLAN Phase 6](features/ai-backtest-tuning/PLAN.md#phase-6--長歷史穩健性驗證post-mvp2022)。**算力 MUST 雲端 GCE overnight。**

- [ ] Gate：MVP holdout 非 `overfit_suspect`
- [ ] P1：補檔（先 2024–2025 pilot，再決定是否補 2022）+ `cache_audit`
- [ ] P2：`DATA_SPLIT.md` fold（季滾 pilot / 月滾完整）+ Phase 6 holdout
- [ ] P3：GCE 跑 `ft003_walkforward`（或批次腳本）→ `robustness_report.md` §1–§10
- [ ] P3b：人類簽核 WFO Gate（net Sharpe、MDD、trade_count 穩定；摩擦 5 點/趟 MUST）
- [ ] P4：v1/v2 決策樹 + Phase 6 holdout 一次（若 v2）
- [ ] **P5.5 Phase 6.5**：Shadow/Paper ≥2–4 週 + `compare_fill_audits`（報告 §11）
- [ ] 運維：kill switch / emergency flatten 演練、日週報、券商 reconciliation 證據

### P0-5 部位真相驅動（已落地 code+測試；UAT gate 待驗）

- [x] timeout=UNKNOWN → `_settling`/`_settle_via_reconcile`；逾時 HALT；entry+exit 全面凍結；kernel 收斂平倉；孤兒→HALT；對帳硬背板 + 快節奏（見 SPEC §4.2.2 不變量 10、[`CHANGELOG.md`](../CHANGELOG.md)、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)）
- [x] **硬上限永不超過 1 口（10:39 事故 RCA）**：entry 永不以 flat 快照判定未成交（D1）；全 kernel 委託單一在途（D2，`_halt_position_unconfirmed(clear_pending=...)`）；收斂以新鮮 debounce 真相定量（D3）。`MockBroker` 加 report-latency 重現 stale-flat。取捨：真正 miss 的 IOC → HALT 停當日新進場（無自動重試）
- [x] **緊急市價 + 縮短未知視窗 + HALT 殘留漏洞封口（30 口 UAT log）**：停損 IOC miss → kernel 唯一市價平倉；收斂平倉改市價；`pending_timeout_sec` 15→1、`reconcile_fast_sec` 2→1；HALT 期間不得以一致讀數清在途平倉
- [x] **雙層狀態機 SETTLING vs HALT（常駐穩定）**：entry miss（穩定 flat 5s）→ 恢復正常、不 sticky 封鎖整天；HALT 僅異常（上限/孤兒/不可讀/連續 miss 熔斷）；`CALLBACK_LATENCY` 量測；`entry_miss_confirm_sec` / `max_consecutive_missed_entries`
- [x] **Layer 2 IOC 終態查詢**：`order_status_query_enabled`（預設 False）+ `order_status_query_timeout_ms`；order worker `update_status(trade)`；8 種 OrderStatus 正規化；`QueryStatusTask`；place-time oid/early-terminal；`test_order_status_query.py`
- [ ] **Layer 2 UAT gate**（開預設前）：order worker 無 `PyBorrowMutError`；query 不阻塞 place_order；callback 競態安全；flag OFF 零 `update_status(trade)` 呼叫（見 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)）
- [ ] **UAT gate**：`CALLBACK_LATENCY` 量測 live vs sim 延遲；確認 live ms 級、entry miss 5s 窗口安全
- [ ] GCE 實機：刻意製造延遲回報（含遲到的成交），確認不再重下、最終 qty ≤ 1、HALT 後只補一張平倉（市價）
- [ ] （已實作 Layer 2，預設 OFF）`order_status_query_enabled`：UAT 驗證後可開，正向區分 Filled/Cancelled 取代純 inference
- owner: `trading-engine`（狀態機）+ `trading-app`（config、UAT 條目）

### UAT 執行 — 人類（API 已就緒）

- [x] 申請永豐**模擬** API（行情 + 帳務 + 交易；UAT 不需 CA）
- [x] Live 節點：**GCE** — 見 [`ops/LinuxOps.md`](ops/LinuxOps.md) §GCE（`setup-dev.sh`、`/etc/tfx-trading/env`、systemd、cron）
- [x] [`uat/APP.md`](uat/APP.md) **Phase 0** 完成（地端）；GCE login smoke 2026-06-23
- [ ] **Phase 1** 首個完整模擬交易日（GCE 自動排程）+ `reports/day*.json` + `sync-from-gce.sh` 回地端
- [ ] Phase 3 起：每週 [`WeeklyStatus.md`](WeeklyStatus.md) + `uat_evidence/templates/*`

### GCP 營運（人類）

- [ ] **2026-07-23**：記錄首月 **GCP 實際花費**（VM `e2-medium`、20GB 磁碟、靜態 IP、egress）；Billing → Reports / Budgets
- [ ] 交易時段 **VM 監控**（GCP Monitoring：08:30–14:00 instance 非 RUNNING → email）；應用 Telegram ≠ 基礎設施告警
- [ ] 磁碟用量（20GB）：`df -h` 或 Ops Agent；tick 成長後評估擴容

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

### P6-SMC-CAL（Live gate — 待 UAT tick）

> **前提**：`structure_filter_enabled` 預設 **false**；與 `trend_filter_enabled` **互斥**（config fail-fast）。開啟前必過 **CAL-8** 人類簽核。
> **設計真相**：[`docs/features/smc-structure-filter/SPEC.md`](features/smc-structure-filter/SPEC.md) · 實作計劃 [`PLAN.md`](features/smc-structure-filter/PLAN.md)

**A 類（合成，已完成）**

- [x] CAL-SMC-1：`structure.py` + `test_structure.py`（FVG/BOS/sweep、gap guard）
- [x] CAL-SMC-2：`regime_allows_entry` 互斥單元測試
- [x] CAL-SMC-3：Phase 3 engine 接線 + `param_sweep` structure grid + stale guards
- [x] CAL-SMC-4：Phase 4 `structure_veto` audit、armed enrichment、`record_structure_veto`、filter-on determinism

**B 類（真實 UAT 資料）**

- [ ] **1. 累積**：UAT 連續 **≥5 交易日**；`TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1`；`tick_cache/*_kbars_*` 可餵 harness；**開 filter 測試時** log 須含 `structure_veto`（預設 filter 關則無）
- [x] **2. Harness**：`structure_calibration_cli`（見 ft PLAN Phase 2）
- [x] **3. Sweep**：`structure_min_strength` grid（`structure_calibration_cli --sweep` + `param_sweep`）
- [x] **4. Counterfactual**：分開跑 — 無濾網 / structure only / trend only（harness 內建；互斥，不得同時開）
- [ ] **5. CAL-8 Go/No-Go**：人類簽核 → [`WeeklyStatus.md`](WeeklyStatus.md)；**No-Go** 則維持 `structure_filter_enabled=false`

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
- [ ] **P4-13-F UAT**：[`uat/APP.md`](uat/APP.md) Phase 4 + 範本 [`uat_evidence/templates/stress_test_record.md`](../uat_evidence/templates/stress_test_record.md)
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
| 證據範本 / 歸檔 | [`uat_evidence/README.md`](../uat_evidence/README.md) |
| Kernel scenario | [`uat/KERNEL.md`](uat/KERNEL.md) |
| 週報 / 人類 follow-up | [`WeeklyStatus.md`](WeeklyStatus.md) |
| 地雲部署 / GCE 規格 | [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md) |
| Linux 運維（GCE / 地端） | [`ops/LinuxOps.md`](ops/LinuxOps.md) |
| Windows 運維 | [`ops/WindowsOps.md`](ops/WindowsOps.md) |
| 架構邊界 | 根 [`SPEC.md`](../SPEC.md) §7 |
| 回測 / sweep 規格 | [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts |
| P6-1 trend 校準（Live gate） | 本檔 §P6-1-CAL + vwap [`SPEC.md` §6.1](../packages/strategies/vwap-momentum/SPEC.md) |
| AI 協作規範 | [`AGENTS.md`](AGENTS.md) |