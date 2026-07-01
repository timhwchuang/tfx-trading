# trading-app — Roadmap

> **執行環境：地雲雙管** — Live 建議 **GCP GCE（asia-east1）** 或 **Windows**；回測/CAL 放 **地端 Linux/macOS**（見 [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md)）。原則：**UAT 驗狀態機與對帳，不驗獲利**。
> **雙軌共識（2026-06-28）**：UAT 持續 = 工程線；**主 focus = Alpha 新 thesis**。現有策略回測均已知不佳 — [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §8。
> 文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。Monorepo：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading)。

## 目前狀態（2026-06-28）

| 階段 | 狀態 |
| ---- | ---- |
| **工程線 · UAT** | **🟢 持續** — 驗狀態機 / fill / 對帳；**不驗策略獲利**（見 [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §8） |
| Phase 0～2 狀態機 / 訊號 / 委託 | ✅ 已落地（kernel + plugin） |
| **Phase 3 UAT** | **🟢 GCE Live 就緒** — [`uat/APP.md`](uat/APP.md) Phase 0 ✅；Phase 1+ 進行中 |
| **GCE Live 節點** | ✅ 已部署（`e2-medium`，Debian 13，asia-east1，08:30–14:00 排程） |
| Phase 4 運維骨架 | ✅ P4-1～12；**P4-13-F**、Telegram 實機待 UAT 演練 |
| **Phase 5 Pilot** | **⛔ 阻塞** — 無合格 alpha；UAT 完成 **≠** 可上 Pilot |
| Phase 6 策略真實化 | 骨架 ✅；**P6-1 / P6-SMC CAL-8** → **放棄**（綁定 vwap-momentum，見 §已放棄） |
| **FT-002 SMC 濾網** | **✅ MVPClosed** — 工程 Phase 1–4 已落地；**CAL-8 / Land 放棄** |
| **Alpha 線** | **主 focus** — Playbook [`ALPHA_RESEARCH_PLAYBOOK.md`](features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md) · 提案 [`THESIS_QUEUE.md`](../workspaces/THESIS_QUEUE.md) |
| **FT-003 回測調參** | **✅ 收尾放棄** — `grid_no_viable_solution`；**不再 sweep** |
| **FT-004～005、007～008** | **✅ MVPClosed / 放棄** |
| **FT-006 VWAP Stretch Fade** | **✅ MVPClosed** — v2.1 train 未過；legacy holdout 未過 |
| **FT-009 ORB** | **✅ MVPClosed** — legacy 過 / 2025 train 負 / holdout 未過 |
| **FT-010 VTP** | **✅ MVPClosed** |
| **FT-011 SCB** | **✅ MVPClosed** |
| Phase 7 策略介面 | ✅ Protocol + `strategy-vwap-momentum`（**UAT smoke only**） |
| Phase 8 / monorepo | ✅ |

> **UAT Ready ≠ Live Ready ≠ Alpha Ready**。Pilot / Live **須**新 thesis 過 v2.1 train gate，不得沿用現有 plugin 回測結論。
**測試基線**：`bash scripts/run-all-tests.sh` — 以實際 `Ran N tests` 輸出為準（2026-06-18：engine **90**、backtest **27**、strategy **60**、app **136**，合計 **313** 全綠）。

### Phase 編號對照（避免混淆）

| 本檔 Roadmap | [`uat/APP.md`](uat/APP.md) 清單 | 意義 |
|--------------|--------------------------------|------|
| Phase 3 UAT | Phase 0–4 | 模擬累積、壓力測試 |
| Phase 5 Pilot | **Phase 5** | 量化 gate + 人類簽核 |
| Phase 6 策略真實化 | Phase 6（切 CA）；~~Live CAL-8~~ **濾網 CAL 已放棄** | trend/structure filter 骨架保留、**永久關** |
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
| K 線落盤 | `KBARS_ARCHIVE=1` | ATR 熱身、HTF 回測；~~CAL-8 B 類~~ **已放棄** |
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
| Trend CAL tooling | `python -m reporting.calibration_cli` | **封存** — P6-1-CAL 已放棄；CLI 保留研究用 |
| SMC CAL tooling | `python -m reporting.structure_calibration_cli` | **封存** — P6-SMC-CAL 已放棄；預設 `structure_filter_enabled: false` |

---

## 目前主 focus（2026-06-28）

| 優先 | 軌道 | 動作 |
|------|------|------|
| **P0** | Alpha | **FT-013** Phase 0a — [`supertrend-flip`](features/supertrend-flip/PLAN.md) CF + tests（P-007 approved） |
| **P1** | UAT 工程 | Phase 1+ 模擬交易日、fill 對帳、P4-13-F、累積 tick |
| — | ~~P2 CAL-8~~ | **放棄** — 濾網綁定 `grid_no_viable_solution` 的 vwap-momentum |
| — | Pilot / Live | **阻塞**，直至 Alpha P0 過關 + 人類 Go |

---

## 已放棄 / 不再進行（2026-06-28）

> SSOT：[`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §8.2。下列 **不得**再排入 sprint。

| 項目 | 原因 |
|------|------|
| FT-003 四 agent **grid sweep / round2** | `grid_no_viable_solution`；`round2_proposal` 已否決 |
| FT-003 **Phase 6 WFO / 長歷史**（§Post-MVP） | 無冠軍、無 holdout 過關；改為 **新 thesis** 才跑 WFO |
| FT-006 **UAT 切換 / valid 上 tune** | holdout 未過；MVPClosed |
| FT-009 **重戰 / plugin 上線** | 2025 train 全負；holdout 結構失敗 |
| FT-010 / FT-011 **plugin** | Phase 0 未過 |
| ORB / SCB / VTP **變體無新編號重跑** | 本質同族；需新假說 |
| **以 vwap-momentum 回測期望推進 Pilot** | hybrid 淨期望全負 |
| **P6-1-CAL / P6-SMC-CAL（CAL-8 B 類）** | trend / SMC 濾網 **僅服務** vwap-momentum；base 已 `grid_no_viable_solution`；開濾網無法創造 alpha |
| **FT-002 Phase 5 Land + CAL-8** | 同上；**程式碼凍結**作研究參考，不再跑 harness 簽核 |
| `elected_config.yaml` / leaderboard 晉級 holdout | 本輪無候選 |
| agent-conservative / execution **現 grid 再 sweep** | 診斷已完成；邊際效益趨零 |

---

## Open items（未完成）

### FT-003 — AI 回測調參（[`PLAN`](features/ai-backtest-tuning/PLAN.md)）

**MVP（2026-01～05，先做）**

- [x] Phase 1：`cache_audit` PASS、`determinism_check` PASS（各 agent）
- [x] Phase 2：MVP 兩位 baseline + `analysis.md` §Baseline
- [x] Phase 3：`ft003_run_sweep.py` + `sweep_result.jsonl` + 五段式 `analysis.md`
- [x] Phase 3.4：雙向 `peer_review_*.md`
- [x] Phase 3.5：`leaderboard.jsonl`
- [x] **Phase 3.6**：四平面診斷 §A–§D 完成；`strategy_diagnosis.md` §1–§7 + **§Decision（Option A）** — 否決 round2、改策略層重設計
- [x] **Phase 3.6 / Phase 4 收尾**：[`election_report.md`](../workspaces/election_report.md) — `grid_no_viable_solution` + `diagnostic_only`（holdout 未跑）
- [x] **Strategy v2 第一波** → FT-004～011 **均已 MVPClosed**；下一 thesis 見 `strategy_diagnosis.md` §8.3
- [x] ~~agent grid 持續 sweep~~ — **放棄**（§已放棄）

### FT-004 — Momentum Continuation（[`PLAN`](features/momentum-continuation/PLAN.md)）— **MVPClosed**

- [x] Phase 0：counterfactual + `mc-baseline` 骨架
- [x] Phase 1：`strategy-momentum-continuation` plugin + tests
- [x] Phase 2：2026-04 baseline + `gate_report.md`（G1–G4）
- [x] Phase 3：人類 **No-Go** — §a arm 調參 + §b adverse guard；見 [`gate_report.md`](../workspaces/mc-baseline/gate_report.md)
- [x] ~~Phase 4 sweep / Phase 5 holdout~~ — **取消**（G1 未過）
### FT-005 — Timeout Continuation（[`PLAN`](features/timeout-continuation/PLAN.md)）— **MVPClosed at Phase 0**

- [x] Phase 0：counterfactual + `tc-baseline/reports/counterfactual_timeout_entry.json`
- [x] Phase 0 決策：**No-Go** — `timeout_tick` gross **4.10**、net **-0.90**（見 [`gate_report.md`](../workspaces/tc-baseline/gate_report.md)）
- [x] ~~Phase 1 plugin~~ / ~~Phase 2 baseline~~ — **取消**
- [x] 下一 thesis → **FT-006** VWAP Stretch Fade

### FT-006 — VWAP Stretch Fade — **MVPClosed · 放棄**

- [x] Phase 0～3、holdout 2026-05 — holdout **未過**（overfit suspect）
- [x] ~~人類簽核後 UAT 切換~~ — **放棄**
- [x] ~~可選 sweep~~ — **放棄**

### FT-007 — Momentum Exhaustion Reversal（[`PLAN`](features/momentum-exhaustion-reversal/PLAN.md)）— **放棄 / MVPClosed**

- [x] Phase 0 v1：1m K pilot — No-Go（n=2）
- [x] Phase 0 v2：tick flow flip — n=108，net **−3.75**
- [x] Phase 0 v3：close_1h / footprint / surge — **全未過**；best v3_all net **−0.07**（n=15）
- [x] 人類 **放棄** — 不跑 01–04、不開 plugin（見 [`gate_report.md`](../workspaces/mer-baseline/gate_report.md)）

### FT-008 — Short Breakout（[`PLAN`](features/short-breakout/PLAN.md)）— **MVPClosed**

- [x] Phase 0 v1/v2 — valid 子集過、01–04 未過

### FT-009 — Opening Range Breakout — **MVPClosed · 放棄**

- [x] SPEC + PLAN + plugin + legacy 01–04 / holdout 05
- [x] **2025 train v2.1 複驗** — 全 param net 負 → **不重戰**
- [x] ~~holdout v2 04–06 翻案~~ — 僅可 **存檔**（06 tick 落地後），不作 UAT 依據

### FT-010 — VWAP Trend Pullback（[`PLAN`](features/vwap-trend-pullback/PLAN.md)）— **MVPClosed**

- [x] Phase 0 CF — 01–03 **未過**（best rcy10 n=3；04 valid 0 筆）
- [x] FT-010b 證偽（去量能濾網）— 仍未過
- [x] **No-Go at Phase 0** — 不開 plugin（見 [`gate_report`](../workspaces/vtp-baseline/gate_report.md)）

### FT-011 — Session Confluence Breakout — **MVPClosed · 放棄**

- [x] Phase 0 CF — 2025 train **未過**；valid Q1 overfit_suspect
- [x] ~~plugin~~ — **取消**

**Post-MVP — FT-003 Phase 6 長歷史** — **⛔ 整段放棄**（無 `elected_config`、無 holdout 過關；新 thesis 過 gate 後另開 WFO）

- [x] ~~Gate：MVP holdout 非 overfit_suspect~~ — 不適用
- [x] ~~P1–P5.5 WFO / Shadow~~ — **放棄**（見 §已放棄）

### P0-5 部位真相驅動（已落地 code+測試；UAT gate 待驗）

- [x] timeout=UNKNOWN → `_settling`/`_settle_via_reconcile`；逾時 HALT；entry+exit 全面凍結；kernel 收斂平倉；孤兒→HALT；對帳硬背板 + 快節奏（見 SPEC §4.2.2 不變量 10、[`CHANGELOG.md`](../CHANGELOG.md)、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)）
- [x] **硬上限永不超過 1 口（10:39 事故 RCA）**：entry 永不以 flat 快照判定未成交（D1）；全 kernel 委託單一在途（D2，`_halt_position_unconfirmed(clear_pending=...)`）；收斂以新鮮 debounce 真相定量（D3）。`MockBroker` 加 report-latency 重現 stale-flat。取捨：真正 miss 的 IOC → HALT 停當日新進場（無自動重試）
- [x] **緊急市價 + 縮短未知視窗 + HALT 殘留漏洞封口（30 口 UAT log）**：停損 IOC miss → kernel 唯一市價平倉；收斂平倉改市價；`pending_timeout_sec` 15→1、`reconcile_fast_sec` 2→1；HALT 期間不得以一致讀數清在途平倉
- [x] **雙層狀態機 SETTLING vs HALT（常駐穩定）**：entry miss（穩定 flat 5s）→ 恢復正常、不 sticky 封鎖整天；HALT 僅異常（上限/孤兒/不可讀/連續 miss 熔斷）；`CALLBACK_LATENCY` 量測；`entry_miss_confirm_sec` / `max_consecutive_missed_entries`
- [x] **Layer 2 IOC 終態查詢（v1/v2，已移除）**：`update_status` 與 terminal hint cache 皆刪除；純 callback-first + `order_deal_records` + L3
- [ ] **Callback-first UAT gate**：整日 sim session → 零 `update_status`、IOC cancel 不 deadlock、部位安全（見 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)）
- [ ] **UAT gate**：`CALLBACK_LATENCY` 量測 live vs sim 延遲；確認 live ms 級、entry miss 5s 窗口安全
- [ ] GCE 實機：刻意製造延遲回報（含遲到的成交），確認不再重下、最終 qty ≤ 1、HALT 後只補一張平倉（市價）
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

### P6-1-CAL — **⛔ 放棄**（綁定 vwap-momentum）

> **2026-06-28**：trend 濾網僅 **否決** vwap-momentum 進場；base 已 `grid_no_viable_solution`。Harness **保留**；**不再**跑 CAL-8 B 類。

- [x] A 類：CAL-1～5、trend harness、sweep tooling
- [x] ~~B 類 UAT 累積 + CAL-8~~ — **放棄**

### P6-SMC-CAL — **⛔ 放棄**（FT-002 · 綁定 vwap-momentum）

> **2026-06-28**：SMC structure 濾網掛在 vwap-momentum **開槍邏輯不變**；base 無 edge → CAL-8 **放棄**。`structure_filter_enabled` **永久維持 false**（直至新 thesis plugin 另議）。

- [x] A 類：CAL-SMC-1～4、harness、sweep、counterfactual tooling
- [x] ~~B 類：≥5 日 UAT + CAL-8 + Land~~ — **放棄**（見 [`smc-structure-filter/PLAN.md`](features/smc-structure-filter/PLAN.md)）

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
| **UAT** | 模擬 API + `simulation: true` + checklist Pass | [`uat/APP.md`](uat/APP.md) |
| **Alpha** | 新 thesis v2.1 train G1–G3 + §3.1 | [`HOLDOUT_CONTRACT_v2.md`](features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) |
| **Pilot** | UAT 工程 Pass + **Alpha 過關** + 人類簽核 | [`uat/APP.md`](uat/APP.md) Phase 5 |
| **Live** | Pilot + 人類簽核 | ~~CAL-8 濾網~~ **已放棄**；[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) |

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