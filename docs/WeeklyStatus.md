# Weekly Status — 人機協作開發日記

> 給**人類**看的進度、Follow-up、待決策。工程路線圖見 [`TODO.md`](TODO.md)；文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。  
> **歷史週報**（2026-06-12～06-16）→ [`ARCHIVE/weekly-status/weekly-status-2026.md`](ARCHIVE/weekly-status/weekly-status-2026.md)

**用法**：重大決策時在下方新增一節（最新放最上面）。

---

### 2026-06-28（FT-004 本回合收尾 — Thesis A No-Go，MVPClosed）

**決策**
- 人類確認 **維持現狀、不 git checkout**；FT-004 以 **MVPClosed**（`thesis_a_no_go`）存檔。
- **Thesis A 結論**：armed 當 tick **全 cohort 即時進場**非可行 Pilot alpha；G1 最佳 gross **+1.89** ≪ 5。
- Plugin **`momentum_continuation` 凍結研究用**；UAT/Live 維持 **`strategy-vwap-momentum`**（已凍結）。

**文件**
- [`SPEC.md`](features/momentum-continuation/SPEC.md) §8 · [`PLAN.md`](features/momentum-continuation/PLAN.md) 收尾 · [`gate_report.md`](../workspaces/mc-baseline/gate_report.md)

**下一方向（未開 ft）**
- timeout-selective entry（只吃 v1 未回踩子集）— 見 [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §6–§7

---

### 2026-06-27（FT-004 No-Go — Arm tune round 1）

**決策**
- 人類確認 **No-Go**；從 gate 備註 **(a)** 開始：提高 `momentum_vol_1s` / ratio 門檻。
- `ft004_arm_threshold_probe.py`（45 combo）→ 最佳 **vol=165** buy=0.80 sell=0.78；counterfactual n=81 gross **+2.33**/趟。
- [`mc-baseline/config`](../../workspaces/mc-baseline/config/config.yaml) 已更新；baseline 重跑：gross **+1.39**、net **-3.61**、194 趟 — **G1/G2/G3 仍未過**。

**Follow-up**
- [ ] Round 1b：單軸 `buy_ratio≥0.85` 或 `vol≥180`（probe 已產物可複用）
- [ ] 或進入選項 **(b)** `max_adverse_atr_k`
- [ ] 更新 [`gate_report.md`](../../workspaces/mc-baseline/gate_report.md) §Decision 若改 thesis

---

### 2026-06-27（FT-004 Phase 0–2 交付 — G1 未過，建議 No-Go 調 arm）

**交付**
- 新 plugin `strategy-momentum-continuation`（武裝當 tick `continuation` 進場 + ATR 出場）。
- Phase 0 counterfactual：235 episodes；全樣本 ATR barrier gross_mean **0.6**、net **-4.4**（摩擦 5 點）。
- Phase 2 baseline（2026-04 valid）：201 趟；gross **-0.02**/趟、net **-5.02**/趟；QSL **0.5%**（G4 過）。
- 產物：[`workspaces/mc-baseline/gate_report.md`](../workspaces/mc-baseline/gate_report.md)。

**診斷**
- v1 **timeout** 子集 counterfactual 強（gross +36/趟），**entered** 子集負（-19/趟）；即時進場全 cohort 仍無正毛 edge。
- vs v1 hybrid（150 趟、QSL 33%）：FT-004 頻率更高、QSL 更低，但 G1/G2/G3 均未過。

**人類必做（Phase 3）**
- [ ] 審閱 `gate_report.md` + counterfactual JSON；填 **§Decision** 簽核欄。
- [ ] 若確認 No-Go：調 arm 門檻 / `max_adverse_atr_k` 後重跑 counterfactual（**不 sweep**）。

---

### 2026-06-27（FT-003 §Decision — Option A：策略層重設計，否決 round2）

**決策**
- 人類確認 **Option A**：不跑 `round2_proposal.md` 出場 grid；接受 `grid_no_viable_solution`。
- 根因：valid 毛期望 ≈ **0**（conservative 冠軍 +0.06/趟）、淨虧幾乎全為摩擦；§6 **逆向選擇**（成交在回踩、順勢行情 timeout 不進場）。
- [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §7 記錄下一步；[`round2_proposal.md`](../workspaces/round2_proposal.md) 標 **已否決**。

**不是打掉重來**
- **保留**：engine、backtest、app、FT-003 診斷工具、`tick_cache`、UAT 骨架。
- **退役**：現 vwap-momentum hybrid 作 Pilot 候選；本輪不產 `elected_config.yaml`。

**人類必做（Follow-up）**
- [ ] **Thesis 二選一**（一頁即可）：breakout 延續 vs 純均值回歸 — 禁止再混 momentum arm + VWAP 回踩。
- [ ] 決定實作殼：新 `strategy-*` plugin vs vwap-momentum v2 分支。
- [x] [`election_report.md`](../workspaces/election_report.md) — `grid_no_viable_solution` + `diagnostic_only`；FT-003 MVP 正式關閉。
- [ ] v2 baseline：valid 毛期望/趟 **> 5** 才進 grid sweep。

---

### 2026-06-27（FT-003 Phase 3.6 四平面診斷收尾 — 待人類簽核）

**狀態**
- Phase 3.6 啟動 Gate 通過：四位 agent `sweep_result.jsonl` + `analysis.md` + 雙向 `peer_review` + `leaderboard.jsonl`（四筆）齊全；`cache_audit --code TMFR1` 診斷月份**無 FAIL**（僅零成交量 tick WARN）。
- 四平面產物齊全：`VOLATILITY_BASELINE.md` §A/B（尺度）、§C（進場漏斗，`ft003_episode_diagnosis.py` 自動填、`entry_funnel.json` 已產）、§D（出場，conservative/execution/risk-exit）。
- 新模組/腳本測試全綠：`test_entry_funnel.py` + `test_ft003_episode_diagnosis.py`（12 項）。
- [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md) §1–§6 合成完成。

**§6 進場漏斗主要結論**
- armed 後「順勢」由 **timeout 子集**貢獻（脈衝單邊跑掉、不回 VWAP）；實際 **entered 子集逆勢回踩成交**（W180 close_delta −15、MAE>MFE）→ armed 順勢 **≠ net edge**。
- 漏斗瓶頸在「價格回到 VWAP band」：`blocked_both` 30.9 萬 ≫ `blocked_vwap_only` 5.7 萬 ≫ `blocked_vol_only` 2.1 千；vol 兩道門非綁定（`ever_vol_dried` 100%）。timeout 67% 從未近 VWAP。
- 回踩深度 p50 ≈ 25 點（≈1×ATR）vs `hard_stop=6`（0.23×ATR）→ **雙重 squeeze**，非單一 knob 可解 → 強化 `grid_no_viable_solution`。

**人類必做（Follow-up — 解鎖 Phase 4）**
- [ ] 閱讀 [`strategy_diagnosis.md`](../workspaces/strategy_diagnosis.md)（尤其 §5 建議 + §6）後，填寫 **§Decision（簽核人 / 日期 / 採納·部分採納·推翻）**。
- [ ] 決策後二選一：(a) 提案第二輪 grid → 完成 [`round2_proposal.md`](../workspaces/round2_proposal.md) §Approval；或 (b) 觸發 Phase 4 holdout 解封（`export FT003_HOLDOUT_UNSEAL=1`，標 `diagnostic_only`）。
- 註：Phase 3.6 診斷產出 **禁止**用於本輪 leaderboard 選參（[`ENTRY_FUNNEL_METRICS.md`](features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) §9）。

---

### 2026-06-26（Layer 2：IOC 終態查詢 — 完善交易環）

**實作**
- **三層真相**：Layer 1 callback（不變）→ Layer 2 `update_status(trade)` on order worker（新增）→ Layer 3 `list_positions` debounce（不變）。
- **`order_status_query_enabled`**（預設 **False**）：flag OFF 行為與 inference 完全相同；ON 時 `working`/`unknown` 仍 fallback Layer 3。
- **`order_status_query_timeout_ms`**（1000）：避免 Shioaji 預設 30s 卡住 order worker。
- **8 種 OrderStatus 正規化** + place-time oid backfill / early terminal。
- 測試：`test_order_status_query.py`（15 cases）；全套綠。

**人類必做（UAT gate — 開預設前）**
- [ ] order worker 重複 `update_status(trade)` 無 `PyBorrowMutError`
- [ ] query 不阻塞 `place_order` 超過 timeout
- [ ] callback + Layer 2 競態無 crash
- [ ] flag OFF 零 `update_status(trade)` 呼叫

見 SPEC §4.2.2 不變量 10、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) Layer 2 節。

---

### 2026-06-26（雙層狀態機：SETTLING 暫態恢復 vs HALT 異常凍結 — 常駐穩定程式）

**思路（IOC live vs sim + HALT 必要性）**
- **Live**：IOC 為交易所撮合核心內建單別，ms 級終結（成交或 Cancelled）。callback timeout = 改用 polling 完成分散式交易，**不應**因偶發靜默 sticky 封鎖整天。
- **Sim**：永豐模擬環境批次撮合/低規主機，回報延遲可達分鐘級 — **不是程式 bug**，不得用來校準 live 行為。UAT==live 設定下，sim 可能觸發 orphan→收斂背板（預期、驗證安全路徑）。
- **HALT 僅用於部位模型異常**：上限 breach、孤兒/非當前成交、券商不可讀、debounce 無法穩定、連續 miss 熔斷。單次 entry miss / 網路抖動 → SETTLING → 恢復。

**修復（已併入 code + 測試 + 文件）**
- **`_resolve_entry_missed`**：entry 穩定 readable-flat 逾 `entry_miss_confirm_sec`（5s）+ debounce → 視為 miss、清 pending、記 WARNING、**恢復正常進場**（不 sticky HALT）。
- **連續 miss 熔斷**：`max_consecutive_missed_entries`（預設 3）→ HALT+CRITICAL（結構性問題）。
- **`CALLBACK_LATENCY` log**：委託/成交 callback 記 `exchange_ts` vs 本地接收延遲，供 UAT 校準。
- 全套綠（trading-engine 173）。見 SPEC §4.2.2 不變量 10、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)「SETTLING vs HALT」表。

**人類必做（UAT gate）**
- [ ] 用 `CALLBACK_LATENCY` 量測 live vs sim 延遲分佈；確認 live ms 級、5s miss 窗口安全。

---

### 2026-06-26（強化：緊急市價平倉 + 縮短未知視窗 + HALT 殘留漏洞封口 — 「最慢多久平倉」與時效）

**問題（30 口 UAT log + 使用者提問）**
- UAT log 玩到 30 口；分析顯示券商把成交/部位回報**延遲數分鐘**（遠超先前假設的 ~18s）。D1 修復可擋住「重 arm 連續進場」的主因，但暴露兩個時效問題：
  1. **未知視窗對 exit 太致命**：硬停損若落入未知視窗（部位已知在虧、只是不知停損單成交與否），等 60s 才收斂 = 整段時間在出血（使用者：「hard stop 進入 60s 窗口 = 整天白賺」）。
  2. **HALT 殘留漏洞**：極端延遲下，HALT 中「未變動且一致」的券商讀數其實只是「平倉單尚未反映的舊部位」，舊 `exit-consistent-clear` 會誤清在途平倉 → 收斂可能再送一張（雖已限 1 口/次，仍會慢速累積）。

**修復（已併入 code + 測試 + 文件；「絕不超過一口」計畫之延伸，不改正常 entry/獲利出場路徑）**
- **緊急市價單（新設定 `emergency_market_orders`，預設 True）**：停損 IOC（`stop_loss`/`stop_loss_vwap`）未成交（Cancelled、無 fill）→ 不再以限價追，kernel 直接送**唯一一張保證成交的市價平倉**（`_maybe_emergency_market_flatten`，單一在途、`_kernel_converging` 繞過凍結）。HALT **收斂平倉**亦改市價。新增 `OrderSignal.market`、adapter `place_market`（Shioaji `MKP` IOC）、`MockBroker` 市價必成交。→ exit/停損的「最慢多久平倉」自未知視窗**脫鉤**（≈ tick 速度 + 一張市價），代價是滑價（停損可接受）。
- **縮短未知視窗**：`pending_timeout_sec` 15→1、`reconcile_fast_sec` 2→1（1s 背景輪詢）。`settle_timeout_sec` 維持 45（entry 不確定不出血，等待確認且永不 re-arm，視窗大對 entry 安全）。**誠實下限**：真正未知視窗由**券商自身回報延遲**決定（`list_positions`/deal callback 都會延遲），單靠縮短本值無法壓到券商延遲以下 — 故 exit 時效改靠市價升級保證。
- **HALT 殘留漏洞封口**：`_apply_pending_broker_truth` 在 `_position_unconfirmed` 期間**不再**以「一致讀數」清在途 exit/平倉；HALT 中 exit 只認真實減倉或明確 Cancelled callback。收斂永不重複送。
- 測試：停損→市價升級、收斂市價（含關閉變體）、HALT 不誤清、MockBroker 市價必成交；全套綠（trading-engine 169、backtest 37、app 252）。細節見 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)、[`CHANGELOG.md`](../CHANGELOG.md)。

**人類必做（Follow-up / UAT gate）**
- [ ] **UAT 驗證市價升級**：實測停損 IOC miss → 市價平倉是否秒級到位；記錄市價滑價分佈（停損可接受但要量化）。
- [ ] **UAT 量測券商回報延遲**：若 `list_positions`/deal 延遲常態為分鐘級，這是基礎設施問題（模擬 API 可能不正常）；正式環境需確認延遲在可接受範圍，否則 entry 會頻繁 HALT。結論回填本節。

---

### 2026-06-26（強化：實盤淨部位硬上限永不超過 1 口 — 杜絕「stale flat 快照」誤判）

**事故（10:39 回放）**
- truth-driven 重構後仍短暫出現 2 口空單。根因：券商把 entry（`100829`）的成交**延遲約 18 秒**才回報，期間 `list_positions` 仍讀到 flat；kernel 誤判「entry 未成交 → 清 pending」，**退出 SETTLING 並解凍策略**，於是重 arm 第二筆 entry（`10082E`），隨後原單遲到成交 + 新單成交 → 空 2。關鍵體悟：**回報延遲視窗內的 flat 快照不是「未成交」的證據**；不變量靠「不確定後永不 re-arm」維持，與券商讀數是否即時無關。

**修復（已併入 code + 測試 + 文件；使用者選 halt_simple + 保守 timeout）**
- **D1 entry 永不以 flat 快照判定未成交**：`_apply_pending_broker_truth` entry 分支移除「broker flat + kernel flat → 清 pending」路徑；entry **只認正向成交**，否則維持 settling，逾時一律 HALT（sticky `block_new_entry`，永不 re-arm）。
- **D2 全 kernel 委託單一在途**：`_halt_position_unconfirmed` 新增 `clear_pending`（預設 False）且具冪等性 — 只有呼叫端確知在途委託已終結（entry IOC 確認 miss）才清 `order_id`；exit/平倉在途一律保留（不清、不 sync），收斂平倉永不重複送。
- **D3 收斂以新鮮 debounce 真相定量**：`_maybe_converge_flatten` 重新讀取並 debounce `list_positions`，以確認 qty 送唯一一張平倉（非可能過時的 kernel belief），保留 `is_pending`/`_settling` 守門。
- **D4 保守 timeout**：`pending_timeout_sec` 8→15、`settle_timeout_sec` 30→45、`reconcile_confirm_reads` 2→3，使常態遲到成交被採用、僅真正 miss/極端延遲才 HALT；正確性不依賴數值。
- `MockBroker` 加 `position_report_delay_sec` / `deal_report_delay_sec` 重現 stale-flat。全套 `bash scripts/run-all-tests.sh` 綠（trading-engine 162、backtest 35、strategy 63、app 252）。細節見 SPEC §4.2.2 不變量 10、[`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)、[`CHANGELOG.md`](../CHANGELOG.md)。

**明確取捨**
- 真正 miss 的 IOC entry 會 HALT 並**停止當日新進場**（無自動重試）。若 UAT 發現 miss 頻繁，未來增強為券商「依委託 id 查狀態」正向區分 Filled/Cancelled，確認 cancel 後再恢復（本版範圍外）。

**人類必做（Follow-up / UAT gate）**
- [ ] **UAT 量測真實回報延遲**：模擬 API 下單→量測 `list_positions` 與 deal callback 各自相對下單的延遲分佈；據實調 `pending_timeout_sec` / `settle_timeout_sec`（目前依實測 ~18s 設定，未知視窗 15+45=60s 遠大於之）。結論回填本節。

---

### 2026-06-26（重構：部位真相驅動執行狀態機 — 杜絕「兩口以上」累積）

**事故（延續）**
- 1 口策略卻又出現 ≥2 口空單。回放：連續 `Pending 超時` 後，舊邏輯把「未知」當「失敗」清掉 pending，策略下一 tick 立刻重下 exit，與遲到的成交回報（孤兒/非當前委託）疊加 → 累積部位。根因有三：(1) timeout 被當成 FAILED；(2) 有 pending 時週期對帳被跳過（最該對帳時反而不對）；(3) 凍結只擋 entry、沒擋 exit。

**修復（已併入 code + 測試 + 文件，方向 B：券商部位為唯一真相 + 持續 poll 收斂）**
- **P0-5 timeout = UNKNOWN**：`_check_pending_timeout` 不再清 pending 重下，改進 `_settling`（保留 `order_id`，遲到成交仍可歸屬），`_settle_via_reconcile` 快速 poll `list_positions` + `reconcile_confirm_reads` 次 debounce 採信；逾 `settle_timeout_sec` → HALT（`_position_unconfirmed`）。
- **不確定全面凍結**：`_validate_order_signal` 與策略 `evaluate` 在 `settling`/`unconfirmed` 時 entry+exit 全擋。
- **kernel 收斂平倉**：HALT 且非 flat → 送唯一一張依真實 qty 的平倉（節流），確認 flat 才解 HALT（`block_new_entry` 維持至日切/人工）。
- **孤兒/非當前委託成交 → HALT**（非僅 `block_new_entry`）。**對帳硬背板**：`broker_qty > max 且 > kernel` → HALT + 收斂。**對帳快節奏**：未確認時 `reconcile_fast_sec`。
- 新設定 `settle_timeout_sec`(30)/`reconcile_fast_sec`(2)/`reconcile_confirm_reads`(2)；`pending_timeout_sec` 語意改為「callback 等待上限後轉主動對帳」。`MockBroker` 加淨部位 + `list_positions()`；回測 replay 驅動 settle/converge/reconcile。
- 全套 `bash scripts/run-all-tests.sh` 綠（trading-engine 158、backtest 33、strategy 63、app 252）。細節見 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)、[`CHANGELOG.md`](../CHANGELOG.md)、SPEC §4.2.2 不變量 10。

**人類必做（Follow-up / UAT gate — 方向 B 成立前提）**
- [ ] **UAT 實測 `list_positions` 反映 fill 的延遲**：在模擬 API 下單→量測券商部位多久反映成交。若對帳通道也嚴重延遲（> `settle_timeout_sec`），收斂會退化為 HALT+人工（計畫已含此 fallback）；據實調整 `settle_timeout_sec` / `reconcile_fast_sec`。結論回填本節。
- [ ] GCE 實機觀察：刻意製造 timeout（延遲回報），確認**不再**重下、最終 qty ≤ 1、HALT 後只補一張平倉。
- [ ] 收到 HALT/`部位未確認` CRITICAL 時，先人工核對券商部位再清 `block_new_entry`。

---

### 2026-06-25（事故：UAT 開盤 24 口 phantom short — 持倉/券商對帳防呆完成）

**事故**
- UAT 連續運行後，某日開盤 `position_sync` 撈到 **24 口 short**，kernel 全程不知情。回放顯示：重連/relogin 後**只重訂報價、未重掛委託/成交回報通道**，報價照進、策略續下單，但 fill callback 全失 → 一直 `pending_timeout` → 以為沒成交而反覆進場累積。之後 stop/exit 只平 1 口、剩 23 口孤兒（exit 成交把 `position_qty` 直接歸零的獨立 bug）。

**修復（已併入 code + 測試 + 文件）**
- **P0-1**：`_on_reconnected`（及 watchdog relogin 經由它）新增 `_resubscribe_trade`，重掛 `subscribe_trade` + `set_order_callback`；失敗即降級 → relogin。
- **P0-2**：孤兒/不符 `order_id` 的成交不再丟棄 → 強制對帳 + `block_new_entry` + CRITICAL。
- **P0-3**：`_check_position_reconcile` 每 `position_reconcile_sec`（預設 60）對帳；漂移以券商為準 + 熔斷 + CRITICAL。
- **P0-4**：`max_position_qty`（預設 1）entry 硬上限。
- **P1-1**：exit 依實際成交量遞減、歸零才 Flat，平倉後 re-sync 確認；kernel 以實際 `position_qty` 為平倉量。
- **P1-2**：sim reconcile 改用 `list_positions` 判定成交，不再純短路。
- 全套 `bash scripts/run-all-tests.sh` 綠（trading-engine 140 tests）。細節見 [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md)、[`CHANGELOG.md`](../CHANGELOG.md)、SPEC §4.2.2。

**人類必做（Follow-up）**
- [ ] GCE 實機驗證：手動觸發一次 relogin 後下單，確認 `委託回報` → `FILL_AUDIT` 仍到；觀察開盤無 phantom 累積。
- [ ] 確認 Pilot 期間 `operations.max_position_qty: 1` 不放大。
- [ ] 收到 `持倉漂移` / `孤兒成交` CRITICAL 時，先人工核對券商部位再清 `block_new_entry`。

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
- 新增 `python -m backfilldata date …`：Shioaji 歷史行情落地 `tick_cache/`（tick + kbar 同目錄）。
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
- [ ] UAT 照常跑（**不必**開 `structure_filter_enabled`）；持續 `KBARS_ARCHIVE=1` 累積 `tick_cache/*_kbars_*`
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
| **KBARS_ARCHIVE** | 建議 UAT 一併開啟，供 ATR 熱身 + **P6-SMC-CAL** harness（`tick_cache/*_kbars_*`）。 |
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