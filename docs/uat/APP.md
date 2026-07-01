# trading-app UAT to Pilot — Sequential Master Checklist (v2 - Hardened)

> **目標**：讓**任何人**（包含未來的你或下一個 AI session）都能**照表抄課**，一步一步、踏實地、**不會漏關鍵步驟**地從模擬環境走到可以上正式 CA 的小規模 Pilot。
> 這份文件是**單一真相來源**（Single Source of Truth）。所有進度、證據、簽名都在這裡或明確連結到這裡。

> **⛔ CAL-8 已放棄（2026-06-28）**：P6-1 / P6-SMC **濾網校準**不再執行 — 因 **vwap-momentum 已 `grid_no_viable_solution`**（濾網無法救活已死的 host；**≠** filter 對新 thesis 普適無效，見 Playbook 附錄 A）。UAT 照常累積 tick/kbar；**不得**以 CAL-8 為 UAT / Pilot gate。SSOT：[`strategy_diagnosis.md`](../../workspaces/strategy_diagnosis.md) §8.2.1 · [`TODO.md`](../TODO.md) §已放棄。

## 目前進度一目瞭然（每天結束必須更新）

| Phase | 狀態 | 完成日期 | 關鍵證據位置 | 負責人簽名 |
|-------|------|----------|--------------|------------|
| **0. 準備與環境** | ☑ | 2026-06-22 | `uat_evidence/phase0/`、`reports/day20260622.json`、`snapshots/config_20260622.yaml`；determinism **deferred** → Phase 1 | tim_chuang |
| **1. Day 1 首次模擬交易** | ☐ | | | |
| **2. 連續 5 日穩定收集** | ☐ | | | |
| **3. 指標計算與日常觀測** | ☐ | | | |
| **4. 壓力測試與操作成熟度** | ☐ | | | |
| **5. Pilot Readiness Gate 審核** | ☐ | | | |
| **6. 切換正式 CA 準備** | ☐ | | | |
| **7. Pilot 執行（1 口規則）** | ☐ | | | |

**目前下一步建議**：**2026-07-02** 起 GCE 以 **`gudt_route_a`** 跑模擬 UAT（`CONFIG_PATH=workspaces/gudt-route-a-baseline/config/config.yaml`）→ 13:54 post-session → 地端 `sync-from-gce.sh` → 簽名 Phase 1

**GCE Live**：見 [`ops/LinuxOps.md`](../ops/LinuxOps.md) §GCE（`e2-medium`，08:30–14:00 排程）。**換策略**：改 `/etc/tfx-trading/env` 的 `CONFIG_PATH` → `systemctl restart tfx-trading`。

**本週重點**：GUDT UAT 首日 — 確認 `gudt_live state=PlanReady` 或 `gudt_skip`；累積 `tick_cache/TMFR1_*.csv`；更新 `snapshots/determinism_YYYYMMDD.txt`；有成交則記 `SPOT_CHECK_LOG`

---

## 強制規範（不可跳過）

### 證據收集與可重現性（每個 Phase 結束必做）
1. 建立以下目錄結構（Phase 0 一次建立）：
   ```
   C:\tfx-trading\
   ├── reports\                  # 所有 JSON 報告
   ├── snapshots\
   │   ├── config_YYYYMMDD.yaml
   │   └── determinism_YYYYMMDD.txt
   ├── tick_cache\               # 原始 tick（已壓縮）
   └── uat_evidence\             # 簽名截圖、log 片段（範本見 repo uat_evidence/templates/）
   ```

2. **每個 Phase 結束強制步驟**（記錄在下方）：
   - `git status && git add reports/ snapshots/ uat_evidence/`
   - `git commit -m "UAT Phase X complete - YYYYMMDD"`
   - 執行 `python -m sweep.determinism_check --date YYYYMMDD` 並把 hash 寫入 snapshots/
   - `cp workspaces/gudt-route-a-baseline/config/config.yaml snapshots/config_YYYYMMDD.yaml`
   - 在本文件表格簽名 + 填證據路徑

3. **與 Kernel Checklist 整合**：
   - 在對應 Phase 必須完成 kernel 對應階段並簽名（見下方表格）。

**核心原則**
- 先驗證**流程、對帳、可重現性**，再談指標。
- MDD / Sharpe / Expectancy 是 Pilot 的**硬門檻**（Phase 5）。
- 所有動作都要有**可驗證的 git commit + determinism hash + config snapshot**。
- 參數凍結期從 Phase 3 開始算，必須有 git 證明。

### 工作目錄與路徑（macOS / Windows 共通）

| 動作 | 目錄 | 備註 |
|------|------|------|
| `python -m live` | `apps/trading-app/src` | 需先 `source` / 設定 `SJ_*` 環境變數 |
| `reporting` / `storage` / `sweep.*` | **monorepo 根** | `PYTHONPATH=apps/trading-app/src`（Windows：`$env:PYTHONPATH=...`） |
| `reports/`、`tick_cache/`、`snapshots/` | monorepo 根 | 勿在 `src/` 下重導向 `reports/day*.json` |

`LOG_FILE` 可在 repo 內（`logs/trading-app-uat.log`）或 repo 外；**勿 commit** log 與金鑰。UAT 模擬只需**模擬** API Key + `simulation: true`（不需 `.pfx`）。

**Phase 0 vs Phase 1 資料門檻**：Phase 0 冒煙（約 10 分鐘）以 log 內 `登入成功`、`ATR` 更新、`DECISION_AUDIT` 為準；`tick_cache/{product_code}_*.csv`（預設 **微台 `TMFR1`**，見 `config.yaml`）可為空或 `written=0`。**Phase 1** 才要求 tick csv >1MB 與完整 `SIGNAL_AUDIT` / `FILL_AUDIT`。

---

## Phase 0 — 準備與環境就緒（Day 0，1-2 小時）

**目標**：環境乾淨、可重現、資料會被正確記錄 + 強制規範就緒。

| 步驟 | 項目 | 完成 ☐ | 精確命令 / 驗證 | 證據 |
|------|------|--------|------------------|------|
| 0.1 | monorepo 根 + 正確分支 | ☑ | `cd C:\tfx-trading && git status && git branch` | `uat_evidence/phase0/setup_20260622.txt`（main @ 5fd5fb8） |
| 0.2 | 執行 setup | ☑ | `bash scripts/setup-dev.sh` | 看到 "editable" 成功 |
| 0.3 | 跑完整測試 | ☑ | `cd apps\trading-app && python run_tests.py` | 冒煙日 1 fail（determinism）；已於 `2d036cd` 修復，現全綠 |
| 0.4 | 確認證據目錄 | ☑ | clone 已含 `reports/`、`snapshots/`、`uat_evidence/`（含 `templates/`、`phase*/`）；缺目錄再 `mkdir` | repo 骨架已存在 |
| 0.5 | 設定模擬環境變數（永不 commit） | ☑ | `SJ_API_KEY` / `SJ_SEC_KEY` / `LOG_FILE=...` / `TICK_ARCHIVE=1` / `KBARS_ARCHIVE=1` | `~/sinotrade/uat-env.sh`（未 commit） |
| 0.6 | 確認 simulation + 建立 log 目錄 | ☑ | `config/config.yaml` 是 true；`mkdir C:\logs` 或 repo `logs/` | `simulation: true`；`logs/trading-app-uat.log` |
| 0.7 | 第一次啟動驗證 | ☑ | `cd apps/trading-app/src && python -m live`（跑 10 分鐘 Ctrl+C） | `live_smoke_20260622.txt`：登入 TXFR1、ATR、`DECISION_AUDIT` |
| 0.7b | 冒煙日報（選做） | ☑ | **monorepo 根**：`PYTHONPATH=apps/trading-app/src python -m reporting "$LOG_FILE" --json > reports/dayYYYYMMDD.json` | `reports/day20260622.json` |
| 0.8 | **強制證據收集** | ☑ | `cp workspaces/gudt-route-a-baseline/config/config.yaml snapshots/config_YYYYMMDD.yaml`；git commit snapshots/（**不含** log、金鑰） | `snapshots/config_20260622.yaml`（Phase 0 時 TXFR1）；commit `91d34ed` |

**完成條件**：0.1–0.8 ☑ + `snapshots/config_20260622.yaml`。Phase 0 **不要求** tick csv >1MB、`storage` 壓縮或 determinism hash（`snapshots/determinism_20260622.txt` = **deferred**，見 Phase 1）。

**Kernel 對應**：完成 kernel Phase A（環境與設定）並簽名： tim_chuang（2026-06-22）

**下一步**：Phase 1。

---

## Phase 1 — Day 1：首次完整模擬交易日（建立基線 + 證據）

**目標**：跑完整一天，驗證流程、落盤、對帳、報告 + 強制收集第一筆可重現證據。

**執行流程**：

> **GCE Live**（目前路徑）：08:30 排程開機 → systemd 自動 `tfx-trading`；收盤 **13:50** root `systemctl stop` → **13:54** `post-session.sh`（見 [`ops/LinuxOps.md`](../ops/LinuxOps.md)）。地端收盤後 `GCE_HOST=<deploy-user>@<IP> bash scripts/linux/sync-from-gce.sh`，再 commit `reports/`、`snapshots/`。Phase 0 證據來自地端冒煙；Phase 1 以 **GCE 當日** `reports/day*.json` 為準。

1. **早盤前（08:30 前）**
   - GCE：確認排程開機 + `systemctl status tfx-trading`（`CONFIG_PATH` 應指向 `gudt-route-a-baseline`）
   - 確認昨日 tick/kbar 已在 `tick_cache/`（GUDT live bootstrap 需要）

2. **盤中**
   - 確認 `tick_cache\{product_code}_YYYY-MM-DD.csv`（預設 `TMFR1`）大小持續增加
   - 觀察至少一筆 SIGNAL_AUDIT（用 `grep "SIGNAL_AUDIT" logs\...` 或報告）

3. **收盤後必做** — GCE 由 cron 執行；地端手動或驗證時從 **monorepo 根**：
   ```powershell
   cd C:\tfx-trading
   $env:PYTHONPATH="apps\trading-app\src"
   python -m storage
   python -m reporting $env:LOG_FILE --json > reports\day$(Get-Date -Format yyyyMMdd).json
   ```

4. **強制 Evidence Collection（Phase 1 結束）**：
   - `git add reports/ snapshots/ uat_evidence/`
   - `git commit -m "UAT Phase 1 Day1 complete - $(Get-Date -Format yyyyMMdd)"`
   - `python -m sweep.determinism_check --date $(Get-Date -Format yyyyMMdd) --mode hash --output snapshots\determinism_$(Get-Date -Format yyyyMMdd).txt`
   - `cp apps\trading-app\config\config.yaml snapshots\config_$(Get-Date -Format yyyyMMdd).yaml`
   - 在上方進度表簽名 + 填證據路徑

**注意**：determinism_check 現在支援 CLI。
推薦執行方式（從 monorepo 根）：
```powershell
$env:PYTHONPATH="apps\trading-app\src"
python -m sweep.determinism_check --date 2026-06-17 --mode hash --output snapshots\determinism_20260617.txt
```
或直接 `python -m ...` 如果 PYTHONPATH 已正確。

**Day 1 完成 Check**（全部 ☐）：
- [ ] 完整 log + `tick_cache\{product_code}_*.csv`（monorepo 根，預設 `TMFR1`）>1MB + 壓縮 `.gz`
- [ ] `reports\day*.json` 存在且含 KPI 欄位：`performance.expectancy.expectancy_per_trade_gross`、`performance.expectancy.expectancy_per_trade_net`、`performance.risk_adjusted.sharpe`、`cumulative_risk.budget_used_pct`
- [ ] 至少一筆 `DECISION_AUDIT`（`momentum_armed`）+ `SIGNAL_AUDIT` + `FILL_AUDIT`
- [ ] git commit + determinism hash + config snapshot 完成
- [ ] 無明顯錯誤

**Kernel 對應**：完成 kernel Phase B1-B2 並簽名： ________________

---

## Phase 2 — 連續 5 個交易日穩定收集（Week 1）

**目標**：建立穩定流程 + 資料量 + 對帳習慣 + 每日證據。

**每日固定 SOP**：
1. 早盤固定時間啟動
2. 盤中至少開 30 分鐘 log
3. 收盤後執行上面 Phase 1 的壓縮 + reporting 指令
4. **每日結束強制 Evidence**（簡化版）：
   - git commit + 記錄 determinism hash（或至少當日 config snapshot）

**Phase 2 完成條件**（全部 ☐）：
- [ ] 連續 5 日都有完整 tick_cache + reports\*.json
- [ ] 連續 5 日 `tick_cache\{product_code}_kbars_*.csv` 有落盤（`KBARS_ARCHIVE=1`；供 ATR 熱身 / HTF 回測）
- [ ] 至少 3 日有實際進場意圖（`SIGNAL_AUDIT` 或 `DECISION_AUDIT` entry path）
- [ ] 無雙 entry / pending 問題
- [ ] 每日都有 git commit + snapshot

**Kernel 對應**：完成 kernel Phase B3-B4 並簽名： ________________

> 三指標週報自 **Phase 3（第 6 交易日）** 起；Phase 2 只需每日 evidence，不必填 KPI 週報。

---

## Phase 3 — 指標計算與日常觀測（引入三指標 + 摩擦對帳）

**從第 6 日開始** 強制追蹤。**參數凍結期從本 Phase 起算**（須有 git 證明）。

**每日/每週固定**（monorepo 根；PowerShell 會展開 `day*.json`）：
```powershell
cd C:\tfx-trading
$env:PYTHONPATH="apps\trading-app\src"
# 週 KPI 趨勢（gross/net、Sharpe、MDD 使用率）— 輸入須為 --json 產出的報告檔
python -m reporting reports\day*.json --trend
# 或從累積 log 看 DAILY_SUMMARY 趨勢（conversion / 日 pnl）
python -m reporting $env:LOG_FILE --trend
```

**強制追蹤項目**（記錄在 [`WeeklyStatus.md`](../WeeklyStatus.md)）：

| 類別 | 欄位 | 說明 |
|------|------|------|
| 績效 | Expectancy **(gross)** | 未扣摩擦；與 net 並列，避免只看 net 掩蓋執行品質 |
| 績效 | Expectancy **(net)** | 含 config `round_trip_friction_points`（若已開啟） |
| 績效 | Sharpe | 依 config `sharpe_period` |
| 風控 | Max DD 使用率 | % of `max_acceptable_mdd_points` |
| 對帳 | **券商日損益 vs log 日損益** | 券商帳務（點）對照 JSON `daily_summaries[-1].pnl.daily_pnl_points`；差異 > 0.5 點須在週報註記 |
| 事件 | near-miss 摘要 | timeout / `trend_veto` / `structure_veto`（僅 filter on）/ 差價未成交；每週至少一筆或標「本週無」 |

**摩擦成本 SOP**（Phase 3 起，非等到 Phase 7）：
1. 每日收盤：`python -m reporting $env:LOG_FILE --json > reports\dayYYYYMMDD.json`
2. `python -m reporting.uat_evidence_export broker reports\day*.json`（log 側自動填入 CSV）
3. 補券商日損益：手填 `uat_evidence\phase3_weekly\broker_reconciliation.csv`，或 `--broker-data` 匯入含 `date,broker_daily_pnl_pts,broker_source_note` 的 CSV
4. 差異 > 0.5 點須在週報註記；Phase 5 審核前須能說明摩擦 gap

**Phase 3 目標**：
- 累積至少 10 個**交易所交易日**（見 Phase 5 樣本定義；0 成交日可計入但須標記）
- 同時觀察 gross / net 期望值分叉（執行與摩擦是否吃掉 edge）
- 建立券商對帳習慣，避免 Pilot 才發現 log 與帳務不一致

**強制 Evidence**：每 3 日一次完整 git + determinism + config snapshot。

---

## Phase 4 — 壓力測試與操作成熟度

**必須執行並有證據的測試**（不可僅打勾；須附 log 片段或截圖至 `uat_evidence/`）：

| 測試 | 執行方式 | 通過標準 | 證據 |
|------|----------|----------|------|
| 斷網暖機期（P4-13） | 盤中斷網 30–60s | 暖機期無新 entry | log + 時間戳 |
| 斷網有倉 | 持倉時斷網 | CRITICAL + 重連後 `sync_positions` 對帳正確 | log + 券商倉位截圖 |
| No-tick 看門狗 | 長時間無 tick | 正確重訂閱 | log |
| 完整對帳 | 收盤比對 | `daily_summaries[-1].pnl.daily_pnl_points` 與券商一致或可解釋 | `uat_evidence/phase3_weekly/broker_reconciliation.csv` |
| tick_type 品質 | 看 `type0_pct` | <40% 或有書面解釋 | 日報 JSON |
| structure_stale（可選 · **封存**） | ~~CAL-8 前 filter-on 演練~~ | kbars 中斷後擋 entry、允許 exit；log 含 `risk_blocked` `block_reason=structure_stale` | **非 UAT 必做**；CAL-8 已放棄 |

> **P6-SMC-CAL — ⛔ 已放棄（2026-06-28）**：工程 Phase 1–4 已落地；**不再**跑 `structure_calibration_cli` 簽核。UAT 期間 **`structure_filter_enabled` 預設 false**，照常累積 tick/kbar 即可。見 [`strategy_diagnosis.md`](../../workspaces/strategy_diagnosis.md) §8.2。

**Tick 品質 × 訊號品質觀測**（Phase 4 起累積，Phase 5 審核必附）：

依當日 `type0_pct` 分層（建議閾值：低 <30%、中 30–40%、高 >40%），每層追蹤：
- 動量→進場 **conversion rate**（`SIGNAL_AUDIT` 中有意圖 vs 實際 `FILL_AUDIT`）
- 該層 **Expectancy (net)** 與 round-trip 筆數

若高 `type0_pct` 日 conversion 明顯偏低或 expectancy 為負，須在 Phase 5 書面說明是否為 tick 品質問題、策略問題，或單日噪音。**不可**在未分層的情況下只用全樣本 KPI 通過 gate。

**分層填表 SOP**：
```powershell
python -m reporting.uat_evidence_export tick reports\day*.json
# 或一次產出 broker + tick：
python -m reporting.uat_evidence_export both reports\day*.json
```
輸出預設：`uat_evidence\phase4_stress\tick_quality_stratification.csv`（含 `type0_pct`、tier、conversion、expectancy）。`notes` 可手動補充。

**Phase 4 強制**：
- 完成所有測試 + 記錄在 `uat_evidence/`（含斷網演練實際執行日期）
- git commit + determinism
- 至少累積 3 個「壓力情境」完整 audit timeline（含 1 個 near-miss），供 Phase 5 人類審閱

**Kernel 對應**：完成 kernel Phase B3–B6 安全測試並簽名；B3–B6 應作為 **regression** 在後續 Phase 有變更時重跑（見 [`KERNEL.md`](KERNEL.md)）。

---

## Phase 5 — Pilot Readiness Gate（硬門檻審核）

**UAT Ready ≠ Pilot Ready** — 只有本 Phase **全部通過 + 人類負責人簽名**，才考慮 `simulation: false` + 正式 CA。

### 樣本定義（交易員視角，避免口徑模糊）

| 術語 | 定義 |
|------|------|
| **交易日** | 台指期有正常日盤交易時段的**交易所日**（含節假日休市除外）；以 `reports\day*.json` 與 `tick_cache` 日期對齊 |
| **0 成交日** | **可計入** 20 交易日總數，但須在審核表單獨列出筆數與原因（無訊號 / 風控擋 / 連線問題等） |
| **round-trip** | 一組進場 + 平倉（含 session flatten）；以 `FILL_AUDIT` 配對計數 |
| **有效交易密度** | 每 **5 個交易日**至少 **8 筆** round-trip；若策略設計為低頻（例如日均 <2 筆），須在審核前提交**書面密度預期**並相應延長累積期，不得用 0 成交日「灌水」通過 20 日門檻 |
| **Regime 覆蓋** | 20 日可能落在單一波動環境；審核時須註記是否含高波動日、重大事件日；**不另設硬門檻**，但須誠實揭露樣本侷限 |

**量化硬門檻**（台指期日內選擇性策略）：

- **樣本**：≥20 交易日 + **80** round-trip（整體）；**最近 10 日 ≥35** 筆
- **Expectancy (net)**：最近窗 > +0.35 點/筆（**必須同時附 gross**；gross 為負而 net 為正 → 須解釋摩擦假設）
- **Sharpe**：> 0.60（使用 config `sharpe_period`）
- **Max DD 使用率**：整個 UAT 最高 < 70% of `max_acceptable_mdd_points`
- **最近窗健康**：最近 10 日 Expectancy (net) > +0.30 且無連續 3 日大虧損
- **零 Critical**：過去 10 交易日完全沒有
- **凍結**：參數完全凍結 ≥10 交易日（git 證明，自 Phase 3 起算）
- **摩擦對帳**：Phase 3 起累積的「券商日損益 vs log」差異已審閱，無未解釋系統性偏差
- **Tick 分層**：Phase 4 的 `type0_pct` 分層觀測已附（見 Phase 4 小節）

### 可重現性與 Fidelity gap（不可只看 hash）

須用 **frozen config + 真實 UAT `tick_cache`** 在 backtest 重現相同 audits；hash 一致是必要條件，**非充分條件**。

已知落差（審核時須主動提及）：
- Backtest 撮合為啟發式 slippage（[`packages/trading-backtest/SPEC.md`](../../packages/trading-backtest/SPEC.md) §9），非 order book
- Live 的 queue position、partial fill、網路延遲可能與回測不同

範例命令（從 monorepo 根）：
```powershell
$env:PYTHONPATH="apps\trading-app\src"

# Pilot gate 自動預檢（量化門檻 + broker/tick CSV + Critical 掃描）
python -m sweep.pilot_gate_check reports\day*.json --log-file $env:LOG_FILE

# 可重現性 hash
python -m sweep.determinism_check --date 2026-06-10 --mode hash

# 壓力情境 audit timeline（含 EXEC pending / position_sync）
python -m reporting $env:LOG_FILE --episodes

# 建議：抽 3 個交易日用 backtest engine 重跑並比對 SIGNAL/FILL audit 序列
```

**Phase 5 強制 Evidence Collection**：
- 完整 git tag 或 commit
- 最新 determinism hash + 至少 3 日 audit 序列比對紀錄
- 書面 Pilot 風險預案 + escalation matrix（誰決定何時 flatten）
- 前 **5 大虧損日**整理（日期、筆數、MDD 貢獻、是否 near-miss 相關）— 供人類親閱
- Phase 3 起累積的摩擦對帳摘要

**審核表**（全部 ☐ + 負責人簽名）：

- [ ] 樣本量達標（含 0 成交日清單 + 有效密度說明）
- [ ] gross + net 三指標達門檻 + 最近窗健康（附 JSON）
- [ ] Tick 品質分層觀測已附且可解釋
- [ ] 所有 Phase 4 壓力測試通過 + `uat_evidence/` 證據
- [ ] **人類已親自 review ≥3 個壓力情境**（含 **≥1 個 near-miss**）的完整 audit timeline + 券商對帳
- [ ] 零 Critical（過去 10 日）
- [ ] 凍結期 + git 證明
- [ ] 可重現性驗證通過（hash + 真實 tick audit 比對）
- [ ] 摩擦對帳無未解釋系統性偏差
- [ ] 書面風險預案 + escalation matrix 簽名
- [ ] 人類負責人親自審閱最差情境 + 前 5 大虧損日

**審核結果**： ☐ 通過（可準備 Phase 6）　☐ 未通過 → 繼續 Phase 2–4 至少 X 日（填寫：____）

---

## Phase 6 — 切換正式 CA 最後驗證

- 申請正式 CA + 設定環境變數
- 把 config 改 `simulation: false`（**只有通過 Phase 5 才改**）
- **驗證步驟**（必須做 + 記錄證據）：
  1. 先用 `simulation: false` 但小規模測試登入 + `sync_positions`
  2. **Alerts 實機驗證**（Ops 責任，對照 [`docs/ops/WindowsOps.md`](../ops/WindowsOps.md) §P4-3）：
     - Telegram / webhook 已設定且 `tests/test_alerts.py` 或手動 `send_alert` 曾成功
     - 盤中或測試環境手動觸發一筆 **CRITICAL**（pending timeout / no-tick 模擬皆可）
     - 確認 log 出現 `ALERT [CRITICAL]` + 終端實際收到訊息
     - **`uat_evidence/` 必附**：訊息截圖 + **UTC+8 時間戳** + 對應 log 行號
  3. **斷線演練複驗**（P4-13）：若 Phase 4 後有 engine/app 變更，須重做一次斷網暖機或有倉情境
  4. 跑一次 `session_force_flatten` / force_flatten 測試（確認 kernel 行為）
  5. 確認 `daily_summaries[-1].pnl.daily_pnl_points` 與券商對帳一致（即使 0 成交）
- 記錄所有步驟 + git commit + 截圖至 `uat_evidence/`

**Kernel 對應**：完成 kernel Phase D 前置 + Phase E sign-off 草稿（見 [`KERNEL.md`](KERNEL.md)）。

### 角色協作備註（Phase 4–7 有效）

| 角色 | 必做 | 文件錨點 |
|------|------|----------|
| **Ops** | Phase 6 告警實機驗證、Live 排程（Windows 或 GCE systemd）、斷線演練證據 | [`HYBRID_DEPLOY.md`](../ops/HYBRID_DEPLOY.md)、[`LinuxOps.md`](../ops/LinuxOps.md)、[`WindowsOps.md`](../ops/WindowsOps.md) |
| **永豐 API / Kernel** | B3–B6 regression；重連後 `sync_positions` + 首 tick 暖機對帳 | [`KERNEL.md`](KERNEL.md)、[`LIVE_SAFETY.md`](../ops/LIVE_SAFETY.md) |
| **Daily Reviewer** | 每週三指標 + gross/net + 摩擦差異 + near-miss；Phase 5 前整理前 5 大虧損日 | [`WeeklyStatus.md`](../WeeklyStatus.md) |

---

## Phase 7 — Pilot 執行規則（上 CA 後）

1. **永遠從 1 口開始**
2. 前至少 15-20 個交易日**絕對不改任何參數**（有 git 凍結證明）
3. 每日產生含三指標的報告 + 更新進度表
4. **觸發立即 review 條件**：
   - 單日虧損接近 daily limit
   - MDD 累積 > 40% budget
   - 出現任何 Critical
5. 每週在 WeeklyStatus 更新「真實摩擦成本 vs 預估」（Phase 3 已開始的對帳在此延續並加強）
6. 只有累積足夠實盤正期望值 + 穩定後，才討論放大口數

**Rollback 預案（可執行清單）**：
當任何一天觸發 review 條件：
1. 立即停止 live 程式（Ctrl+C 或 taskkill）
2. 手動檢查倉位：如果有倉，用券商介面或 script 手動 flatten（記錄券商成交編號）
3. 切回 simulation: true（config.yaml）
4. git tag 或 commit 標記當日 rollback（`git commit -m "Pilot rollback - YYYYMMDD reason: MDD breach"`）
5. 在 WeeklyStatus.md 記錄事件 + escalation matrix 通知（誰負責 review）
6. 至少暫停 3 個交易日，重新跑 UAT 檢查至少 Phase 2-4 部分
7. 只有人類簽名後才可恢復 Pilot

**escalation matrix** 必須事先填好（在 Phase 5 書面預案中）：
- 誰有權決定當日 flatten
- 誰通知團隊
- 資本暴露上限

**注意**：rollback 不是失敗，而是專業的風險控管。

---

## 執行環境統一（Phase 0 強制執行一次）

- 強烈建議從 **monorepo 根** (`C:\tfx-trading`) 執行；`$env:PYTHONPATH="apps\trading-app\src"`。
- 路徑 SSOT：`apps/trading-app/src/storage/cache_paths.py` 定義 `tick_cache/`（tick + kbar）、`reports/`、`snapshots/`、`uat_evidence/`（皆在 monorepo 根）。
- Phase 0 確認目錄存在（clone 已含骨架，見強制規範）。

## 長期資料管理（從 Phase 3 開始遵守）

- tick_cache 保留最近 30-60 日壓縮檔，舊檔可手動歸檔到 NAS/雲端。
- 每週檢查磁碟使用量。
- 報告 JSON 至少保留 90 天 + 靠 git 歷史。
- 重要 snapshot（config + determinism）永遠保留在 git。

## 如何使用這份文件（強制流程）

1. 每天/每個 Phase 結束 → 執行 **強制 Evidence Collection**（git + determinism + snapshot）
2. 更新最上面的進度表 + 簽名 + 填證據路徑
3. 把 artifacts 放在標準目錄
4. 需要我（AI）幫忙時，直接貼「目前進度表」 + 最新 report JSON + determinism hash + 最近 git commit

**文件修訂紀錄（資深交易人員 review 納入）**：
- Phase 3：gross/net 並列 + 券商對帳摩擦追蹤（自 Phase 3 起，非 Phase 7 才開始）
- Phase 4：tick 品質分層觀測 + 壓力情境 audit timeline 累積；**FT-002** `structure_veto` / `structure_stale` 演練（**可選**；CAL-8 已放棄，預設 filter 關）
- Phase 2：`tick_cache/*_kbars_*` 累積列為 SMC harness 前置
- Phase 5：樣本/密度/0 成交日定義、fidelity gap、≥3 壓力情境人類審閱（含 near-miss）
- Phase 6：Ops 告警實機證據格式 + 角色協作表
- determinism_check CLI、執行環境、rollback 清單（沿用）

**加油。我們用可驗證的步驟，一步一步到 Pilot。**
