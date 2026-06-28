# Strategy Diagnosis — FT-003 Phase 3.6

**撰寫日期**：2026-06-27
**Phase 3**：四位 sweep + analysis + peer_review + leaderboard — ✅ 完成
**Phase 3.6**：四平面診斷（尺度 §A/B、進場 §C、出場 §D）— ✅ 完成
**Phase 4 MVP 收尾**：✅ [`election_report.md`](election_report.md) — `grid_no_viable_solution` + `diagnostic_only`（2026-06-27）
**資料 SSOT**：[`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) · Methods：[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)

> 本檔合成四 agent sweep + 市場尺度診斷；**不是** leaderboard、**不是** `elected_config`。
> 契約：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6 · [`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md) Phase 3.6

---

## 1. 四平面 sweep 摘要

| Agent | 冠軍 valid_score | 淨期望/趟 | QSL | 結論（一句） |
|-------|------------------|-----------|-----|--------------|
| agent-conservative | -18.83 | -4.94 | 27.8% | 進場濾網相對最佳，九組仍全負；valid 毛點 +10 但淨 -800 |
| agent-execution | -16.14 | -6.48 | 19.3% | trail=6 + IOC=3 壓低 QSL，毛點仍深度為負 |
| agent-risk-exit | -14.21 | -5.80 | 16.8% | 四軸 valid_score 最佳；出場結構主效應，淨期望仍負 |
| agent-regime | -21.32 | -5.10 | 32.5% | grid 無辨識力、veto 占位；不建議開 filter |

**全平面是否淨負**：☑ 是（已完成 grid 內冠軍淨期望皆 < 0） ☐ 否

---

## 2. 摩擦 vs gross edge

- **摩擦**：5 點/趟（SHARED_ASSUMPTIONS v1.2 §3）。
- **conservative 冠軍**：valid 毛 PnL **+10** 點 / 162 趟 → 毛期望約 **+0.06/趟**；淨 **-4.94/趟** → 摩擦主導。
- **execution 冠軍**：valid 毛 **-221.5** / 150 趟 → 毛期望約 **-1.48/趟**；淨 **-6.48/趟**。
- **baseline（預設 config）**：毛 -48、淨 -798（150 趟）→ 策略邏輯在 valid 區間亦無正 gross edge。

**結論**：即使個別平面改善 QSL 或 valid_score，**淨期望無一為正**；問題非單一平面可解，需尺度與出場結構重設。

---

## 3. 尺度錯配（stop ÷ ATR）

引用 [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) §A：

| 月 | ATR p50 | stop_ratio (HS6) | 備註 |
|----|---------|------------------|------|
| 2026-01 | 15.7 | 38% | 停損約 0.4×ATR |
| 2026-04 valid | 25.7 | 23% | sweep 評估區間 |
| 2026-05 holdout | 33.8 | 18% | 僅風險敘事 |

固定 `hard_stop_points=6`、`trail_points=8` 相對 4 月 ATR 僅 **0.23–0.31×**；相對 1m range p50（25 點）`range_ratio≈0.24`，停損常落在分鐘噪音內。QSL 28–33%（baseline）與 §D 秒停損結構一致。

---

## 4. Holdout 風險（不得引用 5 月回測實績）

- 5 月 ATR p50（33.8）> 4 月 valid（25.7）；`stop_ratio` 降至 **18%**。
- 若維持固定點數出場，holdout 預期 **更緊停損、QSL 升、淨期望惡化**（敘事 only，未跑 5 月回測）。
- 指數 med Close 41k+ vs 4 月 37k → regime 與波動雙漂移。

---

## 5. 建議

- [x] **不推薦** `elected_config` / 標 `grid_no_viable_solution`
- [x] ~~仍跑 Phase 4 holdout~~ — **跳過**（`diagnostic_only`；見 [`election_report.md`](election_report.md)）
- [x] ~~申請第二輪 grid~~ → **否決**（§Decision：Option A，改策略層重設計）

**主瓶頸**：☑ 進場漏斗（結構性回踩不可達）　☑ 出場結構（QSL 高）　☑ 摩擦　☑ 尺度錯配 — 四者交互，**非單一 knob 可解**（見 §6.4）。

---

## 6. 進場漏斗（armed / 回踩 / vol）

引用 [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) §C（`agent-conservative` valid 2026-04，235 episodes）；Methods：[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)。

### 6.1 脈衝是否順勢

| cohort | N | W30 close_delta | W180 close_delta | MFE_180 | MAE_180 |
|--------|---|-----------------|------------------|---------|---------|
| entered | 150 | -5.0 | -15.0 | 28.0 | 41.5 |
| timeout | 85 | +10.0 | +35.0 | 69.0 | 23.0 |

- **entered** 子集 armed 後 **逆**武裝方向漂移（W180 close_delta **-15**），且 MAE(41.5) > MFE(28) — 符合設計：策略**等回踩、不追價**，成交發生在脈衝回吐後。
- **timeout** 子集反而**順勢**走（W180 **+35**，MFE 69）：脈衝單邊延續、價格未回 VWAP → timeout。
- **結論**：armed 後「順勢」統計由 timeout 子集貢獻，**≠ 策略 net edge**（[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) §1.3）。實際成交者進在逆勢回踩、不利偏移大於有利偏移，與 §2 淨期望為負一致。

### 6.2 漏斗瓶頸

轉化率：armed 235 → ever_near_vwap **75.7%** → ever_vol_dried **100%** → both_same_tick **64.7%** → entered **63.8%** / timeout **36.2%**。

- 一旦 near_vwap ∧ vol_dried 同 tick（64.7%），幾乎必成交（63.8%）→ **瓶頸不在進場觸發**，而在「價格回到 VWAP band」。
- near_miss 月累計：`blocked_both` **309,164** ≫ `blocked_vwap_only` **56,619** ≫ `blocked_vol_only` **2,130** → vol-only 阻擋極罕見；主阻擋為 both / vwap_only（**價格遠離 VWAP**）。
- timeout 中 **67.1%** 從未 near_vwap；`time_to_first_band` p50 **72s**、`time_to_entry` p50 **78.5s**（貼近 `momentum_timeout_sec` 邊緣）→ 對應 [`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) §5.4「timeout 高且不回 VWAP → 結構性不匹配、非單一 knob」。

### 6.3 vol_1s 門檻是否合理

- `P(vol_1s ≥ 150)` = **0.3%** → 武裝門檻落在分布**極右尾**（事件型 spike，符合設計）；`vol_1s_at_arm` p50/p90 = **153 / 227** 確認武裝確實命中 spike。
- `P(vol_1s ≤ 15)` = **85.7%**、`ever_vol_dried` = **100%** → 枯竭門檻幾乎恆真，**非綁定限制**；調 `exhaustion_vol` 對漏斗影響有限。
- **判讀**：vol 兩道門不是瓶頸；放寬 vol knob 無法解決「價格不回 VWAP」的結構問題。

### 6.4 與 §3 尺度錯配是否一致

- `pullback_depth` p50 = **25 點** ≈ 4 月 1m range p50（25）≈ ATR20 p50（25.7）→ 回踩深度約 **1×ATR**。
- 但 `hard_stop_points=6` 僅 **0.23×ATR**（§3）→ 進場後極易被分鐘噪音掃損：與 §D `quick_stop_loss_rate` 28–33%、`stop_loss in_grace` 100% 一致。
- **雙重 squeeze**：策略要求約 1×ATR 的回踩才進場，卻只給 0.23×ATR 的停損空間 → 進場結構與出場尺度互相擠壓，**確認非單一 knob 可解**，強化 §5 `grid_no_viable_solution` 結論。

---

## 7. 下一步（Option A — 策略層重設計，非 round2 grid）

> **不是 monorepo 打掉重來**。保留 engine / backtest / app / FT-003 診斷工具 / `tick_cache` / UAT；**退役**現有 vwap-momentum「爆量武裝 + VWAP 回踩」hybrid 作為 Pilot 候選。

| 保留 | 退役 / 凍結 |
|------|-------------|
| `trading-engine` 狀態機、回測、reporting、sweep 框架 | 本輪 `leaderboard` 冠軍 → **不產** `elected_config.yaml` |
| Phase 3.6 診斷產物（§A–§D、`entry_funnel`）作為 v2 設計輸入 | `round2_proposal.md` 出場 grid（否決） |
| UAT 累積 tick（Live gate 仍獨立） | 在現有 hybrid 上繼續 sweep / tune knob |

**建議順序**（見 [`docs/TODO.md`](../docs/TODO.md) §FT-003 收尾 + §Strategy v2）：

1. ~~**FT-003 正式收尾**~~ — ✅ [`election_report.md`](election_report.md)（2026-06-27）
2. **Thesis 二選一**（人類 + 一頁設計）：**breakout 延續**（吃 timeout 子集 MFE）vs **純均值回歸**（不用 momentum arm）— 禁止再混。
3. **出場從第一天 ATR-scaled**（`stop ≈ 0.5–1×ATR`、trail/TP 同尺度）；固定點數僅作研究對照。
4. **降頻目標**：valid 毛期望/趟 **> 5**（壓過摩擦）再談淨正；否則不進 sweep。
5. **實作路徑**：新 strategy plugin（建議 `strategy-vwap-v2` 或新 slug）或 vwap-momentum **v2 分支**；舊 plugin 凍結為研究參考。
6. **驗證**：沿用 FT-003 流程（baseline → valid → 一次 holdout）或精簡版；**新** workspace / grid，不併入本輪 leaderboard。

**FT-004 結論（2026-06-28）**：Thesis A（`momentum_continuation`、armed 當 tick 全進）**No-Go** — 最佳 valid gross **+1.89**/趟（G1 未過）；counterfactual 證實 timeout 子集有 edge、entered 子集負，全進場稀釋。Plugin **凍結**；見 [`mc-baseline/gate_report.md`](mc-baseline/gate_report.md)、[`docs/features/momentum-continuation/SPEC.md`](../docs/features/momentum-continuation/SPEC.md) §8。

**FT-005 結論（2026-06-28）**：Thesis B（timeout 當 tick 進場）**No-Go at Phase 0** — timeout cohort `timeout_tick` CF gross **+4.10**/趟、net **-0.90**；延遲 180s 摧毀 armed 時點 edge（同子集 armed tick **+36**/趟）。Plugin **未實作**；見 [`tc-baseline/gate_report.md`](tc-baseline/gate_report.md)、[`docs/features/timeout-continuation/SPEC.md`](../docs/features/timeout-continuation/SPEC.md) §8。Strategy v2 breakout 路徑（armed / timeout 雙 thesis）**均否決** → 下一 thesis：**均值回歸**。

**FT-006 結論（2026-06-28）**：Thesis C（`vwap_stretch_fade`）legacy valid **G1–G4 過**；holdout 2026-05 **未過**；**v2.1 train 2025 未過**（k=2.0 net **−5.65**）→ **MVPClosed**（`thesis_c_v21_train_no_go`）。見 [`vsf-baseline/gate_report.md`](vsf-baseline/gate_report.md)。

**FT-007 結論（2026-06-28）**：Thesis D（flow flip / 吸收反轉）**人類放棄** — v1/v2/v3 Phase 0 均未過 gate；v3_all 最佳 net **−0.07**（n=15）。Plugin **未實作**。見 [`mer-baseline/gate_report.md`](mer-baseline/gate_report.md)。

**FT-009 結論（2026-06-28）**：Thesis F ORB — legacy 01–04 **通過**（rm30_bk0p15）；**2025 train v2.1 複驗全 param net 負**；05 holdout 未過 → **MVPClosed**。見 [`orb-baseline/gate_report.md`](orb-baseline/gate_report.md)。

**FT-010 結論（2026-06-28）**：Thesis G VTP — Phase 0 **未過**（n≪30）。見 [`vtp-baseline/gate_report.md`](vtp-baseline/gate_report.md)。

**FT-011 結論（2026-06-28）**：Thesis H SCB — 2025 train **未過**（net 負、median 負）；valid Q1 rm30 **overfit_suspect**。見 [`scb-baseline/gate_report.md`](scb-baseline/gate_report.md)。

---

## 8. 雙軌共識（2026-06-28 · 人類 + Agent）

> **一句話**：狀態機再完美，沒有可交易的進出策略就沒有交易事業；**UAT 與 Alpha 並行，但主戰場在 Alpha**。

### 8.1 兩條線，不可混淆

| 軌道 | 目的 | 目前狀態 | 成功標準 |
|------|------|----------|----------|
| **工程線（UAT / Infra）** | 驗證 `TradingEngine`、委託、audit、fill 對帳、tick/kbar 累積 | **持續進行** | Phase 0–4 UAT checklist；**不**以 PnL 過關；**不**含 P6-1 / P6-SMC **CAL-8**（已放棄，§8.2） |
| **Alpha 線（策略研究）** | 找到 **pre-register** 後可 falsify 的進出 edge | **主戰場** | v2.1 train G1–G3 + §3.1；否則 MVPClosed |

**UAT 掛載的 `strategy-vwap-momentum`**：僅作 **plugin 載荷 / 決策路徑 smoke**，**不代表**回測或 Pilot 已驗證獲利。Live 預設 **paper / 最小口數 / 診斷**；不得以「UAT 在跑」推論 alpha 合格。

### 8.2 已知策略狀態（回測結論 · 不作 Pilot 依據）

| ID | 策略 | 回測結論 | UAT / Live |
|----|------|----------|------------|
| FT-003 | `strategy-vwap-momentum` hybrid | **`grid_no_viable_solution`**（淨期望全負） | UAT smoke **only** |
| FT-006 | vwap-stretch-fade | valid 過 / holdout 未過 / **v2.1 train 未過** | MVPClosed |
| FT-009 | ORB | legacy 過 / **2025 train 負** / holdout 未過 | MVPClosed |
| FT-010 | VWAP trend pullback | Phase 0 未過 | MVPClosed |
| FT-011 | Session confluence breakout | Phase 0 未過 | MVPClosed |
| FT-004～005、007～008 | 各 thesis | MVPClosed 或放棄 | — |
| **FT-002** trend / SMC 濾網 + CAL-8 | 綁定 vwap-momentum | **放棄**（`structure_filter_enabled` false） |

**共識**：上表 **無一項** 可作為「已驗證可獲利」的 live 策略；**濾網 CAL-8 亦放棄**。工程線完成 **不** 自動解鎖 Pilot。

### 8.3 Alpha 線下一步（主 focus）

**儀式 SSOT**：[`ALPHA_RESEARCH_PLAYBOOK.md`](../docs/features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md) · 提案佇列 [`THESIS_QUEUE.md`](THESIS_QUEUE.md)

1. **Thesis 提案**：Agent **可**填 queue 草稿；人類 **Pick → `human-approved`** 後才寫 SPEC / 跑 CF（見 Playbook §1.1）。
2. **Phase 0 counterfactual only** — 未過不開 plugin、不進 UAT 替換。
3. **禁止**：在 vwap-momentum 上繼續 sweep knob 指望轉正；禁止 ORB/SCB 變體無新編號重跑；**禁止** P6-1 / P6-SMC **CAL-8**（濾網綁定已失敗 base）。
4. **可並行**：UAT 累積 tick / fill audit → 供未來 **Confirm** 段使用，不取代 train gate。**KBARS_ARCHIVE** 仍可開（通用資料），不為 CAL-8。

---

## §Decision（人類簽核）

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim（對話確認） |
| 日期 | 2026-06-27（FT-003）；**2026-06-28（雙軌共識 §8）** |
| 決策 | **已收尾** — `grid_no_viable_solution` + `diagnostic_only`；**否決** round2；改開 **Option A 策略層重設計** |
| **雙軌（§8）** | **UAT 持續** = 工程驗證 only；**主 focus = Alpha 新 thesis**；現有全部策略回測已知不佳，不得作 Pilot 依據 |
| 備註 | 根因：gross edge ≈ 0 + 進場逆向選擇（§6.1）+ 摩擦 5 點/趟。Phase 4 holdout **未跑**。見 [`election_report.md`](election_report.md)。 |
