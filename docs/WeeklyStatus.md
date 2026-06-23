# Weekly Status — 人機協作開發日記

> 給**人類**看的進度、Follow-up、待決策。工程路線圖見 [`TODO.md`](TODO.md)；文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。  
> **歷史週報**（2026-06-12～06-16）→ [`ARCHIVE/weekly-status/weekly-status-2026.md`](ARCHIVE/weekly-status/weekly-status-2026.md)

**用法**：重大決策時在下方新增一節（最新放最上面）。

---

### 2026-06-23（GCE Live 節點就緒 — Phase 1 待驗）

**目前進度**
- GCP GCE Live 就緒（規格見 [`ops/LinuxOps.md`](ops/LinuxOps.md) §GCE）：`e2-medium`、Debian 13、20GB、排程 **08:30–14:00**（台北）。
- `/opt/tfx-trading`：`setup-dev.sh`、`install-systemd.sh`、`tfx-trading` enabled；模擬登入 smoke OK（`TMFR1`）。
- Cron：root **13:50** `systemctl stop` → tfx **13:54** `post-session.sh`（先 stop 再維護，見 [`ops/LinuxOps.md`](ops/LinuxOps.md)）。
- 手動 post-session 驗證：`reports/day20260623.json`、`snapshots/determinism_20260623.txt`。

**人類必做（Follow-up）**
- [ ] **2026-06-24（下一交易日）**：GCE 自動跑完整 **Phase 1** → 收盤後 `sync-from-gce.sh` 回地端 → 對 `reports/`、`tick_cache`、`determinism` hash
- [ ] **2026-07-23**：記錄首月 GCP 實際帳單（見 [`TODO.md`](TODO.md) §GCP 營運）
- [ ] GCP Monitoring：交易時段 VM 死活 email 告警（Telegram 無法覆蓋 VM 關機）
- [ ] 靜態 IP（若尚未綁定）

**備註**
- VM 上 git：`sudo -u tfx git -C /opt/tfx-trading pull`（repo owner `tfx`）。
- 敏感設定僅在 `/etc/tfx-trading/env`，勿 commit。

---

## UAT 週報必填欄位（Phase 3 起）

每週更新（可併入下方範本）：

| 欄位 | 來源 / 備註 |
|------|-------------|
| Expectancy (gross) / (net) | monorepo 根：`python -m reporting reports\day*.json --trend`（JSON 報告檔） |
| Sharpe、MDD 使用率 | 同上 |
| 券商日損益 vs `daily_summaries[-1].pnl.daily_pnl_points` | `python -m reporting.uat_evidence_export broker reports\day*.json`；差異 >0.5 點須註記 |
| Tick 分層 | `python -m reporting.uat_evidence_export tick reports\day*.json` → `phase4_stress/tick_quality_stratification.csv` |
| near-miss 本週摘要 | timeout / `trend_veto` / `structure_veto`（filter on 時）/ 未成交；無則寫「本週無」 |
| `type0_pct` 偏高日 | conversion / expectancy 是否異常（Phase 4 起） |

Phase 5 審核前另附：**前 5 大虧損日**表（日期、round-trip、當日 net、備註）。

## P6-SMC-CAL 報表模板（CAL-8 用）

跑完 harness 後填（`structure_calibration_cli` + `--friction-enabled`）：

| 欄位 | 來源 |
|------|------|
| 三組 counterfactual `delta_expectancy_net` | CLI 輸出 `no_filter` / `structure_only` / `trend_only` |
| `delta_structure_vs_trend` | CLI `comparison` 區塊 |
| `structure_veto_rate` vs `trend_veto_rate` | 同上 |
| `conversion_30s_rate` | armed → entry 30s |
| `phase3_gate` | 工具提示（人類仍須簽 CAL-8） |
| sweep 最佳 `structure_min_strength` | `--sweep --sweep-output sweep.jsonl` |
| near-miss ≥3（Phase 4+ live `structure_veto`） | 人工審閱摘要 |

**CAL-8 結論**：Go / No-Go + 簽名欄（UAT Ready ≠ Pilot Ready，見 ft SPEC §8.2）

---

### 2026-06-22（backfill 缺口合併 + 模擬 ts 修正）

**目前進度**
- tick RangeTime 補洞：偵測早盤缺口、與既有 `csv`/`csv.gz` **合併**（dedupe `datetime`），寫入 plain CSV 並移除過期 gzip。
- `--overwrite`：只替換請求視窗內 tick，保留視窗外（如夜盤）。
- kbars：API 仍取整日，落地前裁切 `08:45–13:45` 並支援合併；mirror skip path 不再強制覆蓋 `tick_cache` 既有全日 kbar（除非 `--overwrite`）。
- 視窗判定：邊界容忍 1 分鐘（08:46/13:44 視為覆蓋）；若 session 內存在大缺口會強制重抓。
- simulation 舊檔相容：merge 期間會將 legacy `+8h` tick 時間校正回交易所牆鐘。

**人類必做（Follow-up）**
- [ ] 補 `2026-06-22` 早盤：`python -m backfilldata date 2026-06-22 --ticks-only`（無需 `--overwrite` 若僅缺上午）
- [ ] 確認後 `python -m storage` 再壓縮

---

### 2026-06-22（backfilldata 改走 RangeTime 早盤視窗）

**目前進度**
- `backfilldata` tick 預設查詢由 `AllDay` 改為 `RangeTime 08:45:00–13:45:00`，對齊 UAT 補早盤缺口需求。
- CLI 新增 `--time-start` / `--time-end`；若仍需整日 tick，可改用 `--all-day-ticks`。
- `storage.tick_loader`、`backfilldata` 測試與模組文件已同步。

**人類必做（Follow-up）**
- [ ] 補早盤缺口時改用：`python -m backfilldata date <YYYY-MM-DD> --ticks-only`
- [ ] 若要整日資料，明確加：`python -m backfilldata date <YYYY-MM-DD> --all-day-ticks`

---

### 2026-06-22（backfill tick 下載逾時修復）

**目前進度**
- `storage/tick_loader`：`api.ticks(AllDay)` timeout 5s → **30s**，逾時重試最多 3 次（2s 間隔）；修復 `backfilldata date …` 全日 tick 常見 `Timeout: 5000ms` 失敗。
- `storage/kbar_loader`：`api.kbars` 同步 30s timeout。
- 文件：`CHANGELOG.md` trading-app [Unreleased]、`backfilldata/SPEC.md` §6 API mapping。

**人類必做（Follow-up）**
- [ ] 重跑失敗日：`python -m backfilldata date 2026-06-18 --ticks-only`（K 線已存在會跳過）。

---

### 2026-06-22（Phase 1 Day 1 試跑 — 收盤後 partial evidence，不合格）

**目前進度**
- Phase 0 ☑；**Phase 1 Day 1 ☐**（今日為試跑 / 除錯，非簽核日）。
- 收盤後 SOP 已執行：重產 `reports/day20260622.json`、`snapshots/config_20260622.yaml`（TMFR1）、`python -m storage --include-today` → `tick_cache/TMFR1_2026-06-22.csv.gz` + kbars.gz。
- 試跑證據：`uat_evidence/phase1/day1_trial_20260622.txt`。
- **pending / order_id status bug** 已於 `fix/api-borrow-lock` merge（`2adc173`）；今日 log 仍為修復前行為。
- `backfilldata date 2026-06-22` **今日無法跑**（CLI 拒絕當日）；明日起可補 08:45–11:14 tick 缺口。

**試跑數據（TMFR1）**
- `SIGNAL_AUDIT` 6 / `FILL_AUDIT` 0 / `CRITICAL` 3
- tick：26,774 rows，11:14–13:44（缺早盤）
- 日報：entry 3 / exit 3 / completed_rounds 3；expectancy & sharpe = null（無 fill audit）

**人類必做（Follow-up）**
- [ ] **下一交易日**：08:30 前單次 live（新 log、不重啟），驗證 `FILL_AUDIT` ≥1、CRITICAL=0。
- [ ] 2026-06-23 起：`python -m backfilldata date 2026-06-22` 補早盤 tick（勿與 live 同時 login）。
- [ ] 合格 Day 1 收盤後：`determinism_check` + git commit Phase 1 evidence。

**Pending / 待決策**
- 今日是否計入 Phase 2 連續日？→ **否**，待重跑合格 Day 1。

**備註 / 開發日記**
- `determinism_check` 刻意 deferred 至合格 Day 1（與 Phase 0 相同策略）。

---

### 2026-06-22（backfilldata CLI — 歷史 tick/kbar 快取補洞）

**目前進度**
- 新增 `python -m backfilldata date …`：Shioaji 歷史行情落地 `tick_cache/` + `kbar_cache/`（kbar 預設 mirror 至 `tick_cache` 對齊 UAT archiver）。
- 單元測試 + `CHANGELOG` / `SPEC` / `cli_help` 已同步；**已 merge main**（2026-06-22）。

**人類必做（Follow-up）**
- [ ] 收盤後於 UAT 機試跑：`python -m backfilldata date <過去交易日>`（勿與 `python -m live` 同時 login）。
- [ ] 確認 `api.usage()` 流量後再批量補洞（tick 單次 ≤10 日）。

**備註 / 開發日記**
- 日常累積仍以 `TICK_ARCHIVE=1` / `KBARS_ARCHIVE=1` 為主；backfill 僅補歷史缺口。

## 範本（複製用）

```markdown
### YYYY-MM-DD（週次 / 標題一句話）

**UAT 指標（本週）**
- Expectancy gross: ___ / net: ___
- Sharpe: ___ | MDD 使用率: ___%
- 摩擦對帳：券商 vs log 最大單日差異 ___ 點（原因：___）
- near-miss：___

**目前進度**
- 

**人類必做（Follow-up）**
- [ ] 

**Pending / 待決策**
- 

**備註 / 開發日記**
- 
```

---

### 2026-06-18（FT-002 Phase 4 落地 — SMC audit 接線完成）

**目前進度**
- **FT-002** SMC structure filter：工程 **Phase 1–4** 完成（`REVIEW.md` 各 Phase PASS）；`structure_filter_enabled` 預設 **false**。
- 策略：`regime_allows_entry`、`structure_veto` / armed structure DECISION_AUDIT、`structure_stale` → `risk_blocked`。
- App：`record_structure_veto`、`uat_report` 辨識 `structure_veto`；filter-on 3-run determinism 通過。
- `bash scripts/run-all-tests.sh` 全綠（**313** tests：engine 90 / backtest 27 / strategy 60 / app 136）。

**人類必做（Follow-up）**
- [ ] UAT 照常跑（**不必**開 `structure_filter_enabled`）；持續 `KBARS_ARCHIVE=1` 累積 `kbar_cache/`
- [ ] ≥5 交易日後跑 `structure_calibration_cli` + 填本檔 **P6-SMC-CAL 模板** → CAL-8 簽核
- [ ] 若 CAL-8 前要做 filter-on 演練：互斥確認（不可與 trend 同開）+ `structure_stale` log 演練

**Pending / 待決策**
- CAL-8 Go/No-Go（統計優勢未證實前維持 filter 關）
- Phase 5 Land：§9 跨 package SPEC 併入（engineering 待辦）

**備註**
- **UAT Ready ≠ CAL-8 Go ≠ Pilot Ready**（ft SPEC §8.2）
- Harness / sweep 已就緒；B 類 blocked 在 UAT 累積

---

### 2026-06-18（模擬 API 金鑰就緒 — UAT Phase 0 開跑）

**目前進度**
- 永豐**模擬** API 金鑰已備妥；工程 blocker 解除。
- `bash scripts/run-all-tests.sh` 全綠（**313** tests；含 reporting JSON trend 測試）。
- 證據骨架：[`uat_evidence/`](../uat_evidence/)（範本 + phase 子目錄）、`reports/`、`snapshots/`。
- UAT 清單已補強：gross/net、摩擦對帳、tick 分層、壓力情境審閱（見 [`uat/APP.md`](uat/APP.md)）。

**人類必做（Follow-up）**
- [ ] Live 節點（GCE 或 Windows）：`setup-dev.sh` + `SJ_API_KEY` / `SJ_SEC_KEY` / `TICK_ARCHIVE=1` / `KBARS_ARCHIVE=1` / `LOG_FILE`（見 [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md)）
- [ ] 完成 [`uat/APP.md`](uat/APP.md) Phase 0（含首次 `python -m live` 10 分鐘）
- [ ] Phase 1 首個完整交易日 → `reports/day*.json` + determinism hash
- [ ] Phase 3 起建議 `friction.enabled: true`；每週填 `uat_evidence/templates/weekly_kpi_snapshot.md`

**Pending / 待決策**
- 舊四 repo GitHub Archive（仍待人類操作）
- P4-13-F 斷網實機、Phase 6 Telegram 實機 — 待 Phase 4/6 演練

**備註**
- **尚未落地、不阻擋 UAT**：P2-1 多口、P6-4 sizing、P6-5 追價、NDJSON sink、FT-001 audit replay（規劃中）。
- **UAT 即可用**：tick/kbar archive、reporting KPI、determinism_check、near-miss、P4-13 護欄、calibration_cli（trend 預設關）。

---

### 2026-06-17（Monorepo 遷移完成 + 文件/Windows 路徑對齊）

**目前進度**
- **`timhwchuang/tfx-trading`** monorepo 已上線；tag `v0.3.0-monorepo`；CI 綠燈。
- 路徑：`packages/trading-engine`、`packages/trading-backtest`、`packages/strategies/vwap-momentum`、`apps/trading-app`。
- 整合文件：[`SPEC.md`](../SPEC.md)（§7 架構）、[`DOC_MAP.md`](DOC_MAP.md)。
- Windows 預設：`C:\tfx-trading`（venv 在 repo 根）；live 從 `apps\trading-app\src`。
- 舊四 repo README 封存橫幅已 push；**Archive 操作由人類在 GitHub 完成**。

**人類必做（Follow-up）**
- [x] 兩台電腦改 `git clone git@github.com:timhwchuang/tfx-trading.git`
- [ ] Windows UAT 機：clone 至 `C:\tfx-trading` → `bash scripts/setup-dev.sh`（或手動 venv + editable install）
- [ ] 舊四 repo GitHub **Archive**（Settings → Archive）
- [ ] UAT B3b：斷網暖機 / 有倉 CRITICAL（P4-13）

**備註**
- 安裝：`bash scripts/setup-dev.sh`；全測：`bash scripts/run-all-tests.sh`。
- 舊 `UPGRADE_RUNBOOK.md` 已 deprecated。

---

## 長期提醒（跨週有效）

| 項目 | 說明 |
| ---- | ---- |
| **Monorepo** | [`tfx-trading`](https://github.com/timhwchuang/tfx-trading) — `bash scripts/setup-dev.sh`；見 [`SPEC.md`](../SPEC.md) |
| **永豐模擬 API** | **金鑰已就緒**（2026-06-18）；UAT 不需 CA。 |
| **UAT 累積 tick** | `TICK_ARCHIVE=1` 每日落盤 → repo 根 `tick_cache/`。 |
| **KBARS_ARCHIVE** | 建議 UAT 一併開啟，供 ATR 熱身 + **P6-SMC-CAL** harness（`kbar_cache/`）。 |
| **P6-SMC-CAL** | 工程 Phase 1–4 ✅；CAL-8 待 ≥5 日 UAT + 人類簽核；見 [`TODO.md`](TODO.md) §P6-SMC-CAL |
| **UAT 執行** | Phase 0 開跑 → [`uat/APP.md`](uat/APP.md)；證據 [`uat_evidence/`](../uat_evidence/) |
| **Phase 6 CAL B 類** | 待 UAT tick；見 [`TODO.md`](TODO.md) §P6-1-CAL + vwap [`SPEC.md` §6.1](../packages/strategies/vwap-momentum/SPEC.md) |
| **Pilot 門檻 SSOT** | [`uat/APP.md`](uat/APP.md) Phase 5（其他檔僅摘要） |
| **週報 KPI** | Phase 3 起：gross/net + 券商對帳 + near-miss（見本檔「UAT 週報必填欄位」） |
| **文件分層** | 架構 → 根 [`SPEC.md`](../SPEC.md) §7；週報 → 本檔；可開工 → [`TODO.md`](TODO.md) |

---

### 2026-06-17（P0/P4-13 落地 + v0.2.2 發布）

> *（遷移前四-repo 紀錄；現行開發在 `tfx-trading` monorepo。）*

**目前進度**
- **P0 `atr_stale`** + **P4-13** 已實作：engine v0.2.2、strategy v0.1.2、app v0.1.2。
- 暖機：重連後**首筆 tick** 起算。

**人類必做（Follow-up）**
- [ ] UAT B3b（見上節）

---

### 2026-06-17（資料流釐清 + P6-1 暫緩 + Nautilus 借鏡）

**目前進度**
- Live 熱路徑在記憶體；`TICK_ARCHIVE=1` 非同步落盤；策略只吃 `MarketSnapshot`。
- **P6-1**：維持 `trend_filter_enabled: false`；UAT 後用 `trend_veto` audit 再評估。
- Nautilus 借鏡：event catalog + cache 抽象；不借 Rust 熱路徑 / MQ。

**Pending**
- HTF / NDJSON：待 UAT tick。

**Live 連線護欄（P4-13，已落地）**
- 暖機期禁止新 entry；單日斷線 ≥3 → `block_new_entry`；有倉斷線 → CRITICAL。

---

### 2026-06-16（文件重構 — archive）

**目前進度**
- BackTestingSpec 拆至各 package；WeeklyStatus 舊節 → `ARCHIVE/`。

*詳見 [`ARCHIVE/weekly-status-2026.md`](ARCHIVE/weekly-status-2026.md)。*