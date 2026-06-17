# trading-app UAT to Pilot — Sequential Master Checklist (v2 - Hardened)

> **目標**：讓**任何人**（包含未來的你或下一個 AI session）都能**照表抄課**，一步一步、踏實地、**不會漏關鍵步驟**地從模擬環境走到可以上正式 CA 的小規模 Pilot。
> 這份文件是**單一真相來源**（Single Source of Truth）。所有進度、證據、簽名都在這裡或明確連結到這裡。

## 目前進度一目瞭然（每天結束必須更新）

| Phase | 狀態 | 完成日期 | 關鍵證據位置 | 負責人簽名 |
|-------|------|----------|--------------|------------|
| **0. 準備與環境** | ☐ | | | |
| **1. Day 1 首次模擬交易** | ☐ | | | |
| **2. 連續 5 日穩定收集** | ☐ | | | |
| **3. 指標計算與日常觀測** | ☐ | | | |
| **4. 壓力測試與操作成熟度** | ☐ | | | |
| **5. Pilot Readiness Gate 審核** | ☐ | | | |
| **6. 切換正式 CA 準備** | ☐ | | | |
| **7. Pilot 執行（1 口規則）** | ☐ | | | |

**目前下一步建議**：_______________________________

**本週重點**：_______________________________

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
   └── uat_evidence\             # 本 checklist 簽名截圖、log 片段
   ```

2. **每個 Phase 結束強制步驟**（記錄在下方）：
   - `git status && git add reports/ snapshots/ uat_evidence/`
   - `git commit -m "UAT Phase X complete - YYYYMMDD"`
   - 執行 `python -m sweep.determinism_check --date YYYYMMDD` 並把 hash 寫入 snapshots/
   - `cp apps/trading-app/config/config.yaml snapshots/config_YYYYMMDD.yaml`
   - 在本文件表格簽名 + 填證據路徑

3. **與 Kernel Checklist 整合**：
   - 在對應 Phase 必須完成 kernel 對應階段並簽名（見下方表格）。

**核心原則**
- 先驗證**流程、對帳、可重現性**，再談指標。
- MDD / Sharpe / Expectancy 是 Pilot 的**硬門檻**（Phase 5）。
- 所有動作都要有**可驗證的 git commit + determinism hash + config snapshot**。
- 參數凍結期從 Phase 3 開始算，必須有 git 證明。

---

## Phase 0 — 準備與環境就緒（Day 0，1-2 小時）

**目標**：環境乾淨、可重現、資料會被正確記錄 + 強制規範就緒。

| 步驟 | 項目 | 完成 ☐ | 精確命令 / 驗證 | 證據 |
|------|------|--------|------------------|------|
| 0.1 | monorepo 根 + 正確分支 | ☐ | `cd C:\tfx-trading && git status && git branch` | |
| 0.2 | 執行 setup | ☐ | `bash scripts/setup-dev.sh` | 看到 "editable" 成功 |
| 0.3 | 跑完整測試 | ☐ | `cd apps\trading-app && python run_tests.py` | 全部 Pass |
| 0.4 | 建立強制目錄結構 | ☐ | `mkdir -p reports snapshots uat_evidence` | |
| 0.5 | 設定模擬環境變數（永不 commit） | ☐ | `SJ_API_KEY` / `SJ_SEC_KEY` / `LOG_FILE=C:\logs\trading-app-uat.log` / `TICK_ARCHIVE=1` / `KBARS_ARCHIVE=1` | |
| 0.6 | 確認 simulation + 建立 log 目錄 | ☐ | `config/config.yaml` 是 true；`mkdir C:\logs` | |
| 0.7 | 第一次啟動驗證 | ☐ | `cd apps\trading-app\src && python -m live`（跑 10 分鐘 Ctrl+C） | 看到策略啟動 + ATR 更新 |
| 0.8 | **強制證據收集** | ☐ | git commit + 建立第一個 snapshots/ | |

**完成條件**：以上全部 ☐ + 至少一個 git commit + snapshots/ 有東西。

**Kernel 對應**：完成 kernel Phase A（環境與設定）並簽名： ________________

**下一步**：Phase 1。

---

## Phase 1 — Day 1：首次完整模擬交易日（建立基線 + 證據）

**目標**：跑完整一天，驗證流程、落盤、對帳、報告 + 強制收集第一筆可重現證據。

**執行流程**：

1. **早盤前（08:30 前）**
   - 確認所有環境變數
   - `cd apps\trading-app\src && python -m live`

2. **盤中**
   - 確認 `tick_cache\TXFR1_YYYY-MM-DD.csv` 大小持續增加
   - 觀察至少一筆 SIGNAL_AUDIT（用 `grep "SIGNAL_AUDIT" logs\...` 或報告）

3. **收盤後必做（15:00 後）**：
   ```powershell
   cd C:\tfx-trading\apps\trading-app\src
   python -m storage.compress
   python -m reporting C:\logs\trading-app-uat.log --json > ..\..\reports\day$(Get-Date -Format yyyyMMdd).json
   ```

4. **強制 Evidence Collection（Phase 1 結束）**：
   - `git add reports/ snapshots/ uat_evidence/`
   - `git commit -m "UAT Phase 1 Day1 complete - $(Get-Date -Format yyyyMMdd)"`
   - `python -m sweep.determinism_check --date $(Get-Date -Format yyyyMMdd) --mode hash --output ..\..\snapshots\determinism_$(Get-Date -Format yyyyMMdd).txt`
   - `cp ..\..\apps\trading-app\config\config.yaml ..\..\snapshots\config_$(Get-Date -Format yyyyMMdd).yaml`
   - 在上方進度表簽名 + 填證據路徑

**注意**：determinism_check 現在支援 CLI。
推薦執行方式（從 monorepo 根）：
```powershell
$env:PYTHONPATH="apps\trading-app\src"
python -m sweep.determinism_check --date 2026-06-17 --mode hash --output snapshots\determinism_20260617.txt
```
或直接 `python -m ...` 如果 PYTHONPATH 已正確。

**Day 1 完成 Check**（全部 ☐）：
- [ ] 完整 log + tick_cache >1MB + 壓縮 .gz
- [ ] reports\day*.json 存在且含 DAILY_SUMMARY + 三指標
- [ ] 至少一筆 SIGNAL_AUDIT + FILL_AUDIT
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
- [ ] 至少 3 日有實際進場意圖（SIGNAL_AUDIT）
- [ ] 無雙 entry / pending 問題
- [ ] 每日都有 git commit + snapshot
- [ ] 開始在 WeeklyStatus.md 記錄每日三指標趨勢

**Kernel 對應**：完成 kernel Phase B3-B4 並簽名： ________________

---

## Phase 3 — 指標計算與日常觀測（引入三指標）

**從第 6 日開始** 強制追蹤。

**每日/每週固定**：
```powershell
python -m reporting reports\day*.json --trend
```

**強制追蹤項目**（記錄在 WeeklyStatus）：
- Expectancy (net)
- Sharpe (依 config sharpe_period)
- Max DD 使用率 (% of max_acceptable_mdd_points)

**Phase 3 目標**：
- 累積至少 10 交易日
- 開始看到三指標趨勢
- 建立摩擦成本意識

**強制 Evidence**：每 3 日一次完整 git + determinism + config snapshot。

---

## Phase 4 — 壓力測試與操作成熟度

**必須執行並有證據的測試**：

| 測試 | 執行方式 | 通過標準 | 證據 |
|------|----------|----------|------|
| 斷網暖機期 | 盤中斷網 30-60s | 無新 entry | log + 報告 |
| 斷網有倉 | 同上 | 正確對帳 | |
| No-tick 看門狗 | 長時間無 tick | 正確重訂閱 | |
| 完整對帳 | 收盤比對 | daily_pnl 合理 | |
| tick_type 品質 | 看 type0_pct | <40% 或有解釋 | |

**Phase 4 強制**：
- 完成所有測試 + 記錄在 uat_evidence/
- git commit + determinism

**Kernel 對應**：完成 kernel 對應安全測試並簽名。

---

## Phase 5 — Pilot Readiness Gate（硬門檻審核）

**只有全部通過 + 人類簽名，才考慮 simulation: false + 正式 CA。**

**調整後的務實硬門檻**（台指期日內選擇性策略）：

- **樣本**：至少 20 個交易日 + 80 筆 round-trip（整體）；最近 10 日至少 35 筆
- **Expectancy (net)**：最近窗 > +0.35 點/筆（同時看 gross）
- **Sharpe**：> 0.60（明確使用 config 裡的 sharpe_period）
- **Max DD 使用率**：整個 UAT 最高 < 70% of max_acceptable_mdd_points
- **最近窗健康**：最近 10 日 Expectancy > +0.30 且無連續 3 日大虧損
- **零 Critical**：過去 10 個交易日完全沒有
- **凍結**：參數完全凍結至少 10 個交易日（有 git 證明）
- **可重現**：能用 frozen config + tick_cache 在 backtest 重現相同 audits。
  範例命令（從 monorepo 根）：
  ```powershell
  python -m sweep.determinism_check --date 2026-06-10 --mode hash
  # 或比對：用 backtest engine 跑並比對 audit hash
  ```
  附上 determinism hash 在審核表。

**Phase 5 強制 Evidence Collection**：
- 完整 git tag 或 commit
- 最新 determinism hash
- 書面 Pilot 風險預案 + escalation matrix（誰決定什麼時候 flatten）
- 所有 near-miss + 前 5 大虧損的人類審閱紀錄

**審核表**（全部 ☐ + 負責人簽名）：

- [ ] 樣本量達到
- [ ] 三指標達到門檻 + 最近窗健康（附 JSON）
- [ ] 所有壓力測試通過 + 證據
- [ ] 零 Critical（過去 10 日）
- [ ] 凍結期 + git 證明
- [ ] 可重現性驗證通過 + determinism hash
- [ ] 書面風險預案簽名
- [ ] 人類負責人親自審閱最差情境

**審核結果**： ☐ 通過（可準備上 CA）　☐ 未通過 → 繼續 Phase 2-4 至少 X 日

---

## Phase 6 — 切換正式 CA 最後驗證

- 申請正式 CA + 設定環境變數
- 把 config 改 `simulation: false`（**只有通過 Phase 5 才改**）
- **驗證步驟**（必須做 + 記錄證據）：
  1. 先用 simulation=false 但小規模測試登入 + sync_positions
  2. **Alerts 驗證**（具體）：
     - 確保 Telegram / webhook 已設定（見 [`docs/ops/WindowsOps.md`](../ops/WindowsOps.md)）
     - 手動觸發一筆 CRITICAL（例如用測試 script 模擬 pending timeout 或 no-tick）
     - 確認 log 出現 CRITICAL + 實際訊息在 Telegram 收到（記錄時間戳）
  3. 跑一次 force_flatten 測試（確認 kernel 行為）
  4. 確認 daily_pnl 計算與券商對帳一致（即使 0 成交）
- 記錄所有步驟 + git commit + 截圖到 uat_evidence/

**Kernel 對應**：完成 kernel 最終安全 gate。

---

## Phase 7 — Pilot 執行規則（上 CA 後）

1. **永遠從 1 口開始**
2. 前至少 15-20 個交易日**絕對不改任何參數**（有 git 凍結證明）
3. 每日產生含三指標的報告 + 更新進度表
4. **觸發立即 review 條件**：
   - 單日虧損接近 daily limit
   - MDD 累積 > 40% budget
   - 出現任何 Critical
5. 每週在 WeeklyStatus 更新「真實摩擦成本 vs 預估」
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

- 強烈建議從 **monorepo 根** (`C:\tfx-trading`) 執行。
- `tick_cache` / `reports` / `snapshots` 位置由 `apps/trading-app/src/storage/cache_paths.py` 控制（預設相對 app）。
- 範例：先 `cd C:\tfx-trading` ，再用 `python -m` 或 `PYTHONPATH=apps/trading-app/src python -m ...`
- Phase 0 時建立標準目錄（見強制規範）。

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

**本次已補進去的 TOP1~5（現階段可執行部分）**：
- determinism_check 現在有基本 CLI（見下）
- 統一執行環境 + 路徑說明 + 長期備份小節
- Phase 6 alerts 驗證具體步驟
- Phase 7 rollback 可執行清單
- Phase 5 加強可重現性命令範例

**加油。我們用可驗證的步驟，一步一步到 Pilot。**