---
id: META-REVIEW-BRIEF
parent: ALPHA-PLAYBOOK
version: 1.0
status: TXF-Responded
opened: 2026-06-30
owner: human+agent
---

# Playbook v1.6 Meta-Review Brief — 資深 TXF 檢討包

> **狀態**：**TXF-Responded**（2026-06-30）

## 總裁決（Executive Summary）

**Playbook v1.6/v1.7 沒有系統性誤殺真信號。** 全 FT holdout 未過，主因是 **valid regime 不支撐**，不是 G1/G2 算錯。FT-018 是 **near-miss 標竿**，不是應復活的 champion。

| 類別 | 裁決 |
|------|------|
| **必留** | G1/G2、§C 五陷阱、2025 train 封印、skew G-SK 套件、valid 硬擋、禁第三 exit、**payoff_min 2.5** |
| **改（v1.7 已對方向）** | net_total 第一頁、outcome_class、Joint J2、Class Appeal、near-miss registry |
| **廢除** | **無** — 不建議下放 G1 或 skew payoff 門檻 |

### §E 六題摘要

| 題 | 裁決 |
|----|------|
| **E1** FT-018 skew payoff | **Revise**（流程）— skew 賽道正確保守；Class Appeal **Approve** 機制，結案仍 MVPClosed，只讀 mean_robust 複審已通過次級 DQ，不開 plugin |
| **E2** G1 gross>5 | **Approve** 必留 · **Reject** gross_total 年化作主判 · **Approve** 雙軌（已落地） |
| **E3** Joint Fingerprint J1+J2 | **Approve** |
| **E4** outcome_class 分層 | **Approve** L0–L4 |
| **E5** Near-miss registry | **Approve** closure_review（TXF 簽名、禁 tune） |
| **E6** 禁第三 exit FT | **Approve** — GDC entry P0 可 reuse 於新進場 thesis，不可再換 exit |

---

## A. 元問題

Playbook v1.6 + Holdout v2.2.1 在「防 overfit」時，是否 **誤殺真信號**？

| 我們以為做對 | 審計質疑 |
|--------------|----------|
| G1 gross>5 / G2 net>0 壓過摩擦 | 低頻厚尾 **mean 正、median≤0** 被 §3.1 殺；**net_total 正** 仍 MVPClosed |
| Fingerprint 0c-1 省 grid 時間 | W900 正、契約 gross<2（FT-019）→ 假希望後仍跑/敘事混亂 |
| skew 賽道救厚尾 | FT-018 train G1/G2 過、net_total **+173.9**，僅 payoff<2.5 → `no_skew_champion` |
| MVPClosed 一致結案 | `spec_anchor_mismatch` 與 `no_skew_champion` 人類 15 分鐘難分辨 |
| 2025 全年 train 防切片 | legacy 01–04 過、2025 全負（ORB/VSF）— 切片幻覺有抓到，但 **near-miss 無登錄** |

**請 TXF 裁決**：哪些規則 **必留**、**改門檻**、**廢除**？

---

## B. 全 FT Train 帳面表（契約出場 · 摩擦 5 點）

> 區間：**2025-01-01～2025-12-31**（v2.1 train），legacy 案另註。  
> 指標：`net_total` = 全年合計淨點數；**非** stop-less、**非** `horizon_*`。

| FT | 最佳變體 | n | gross_total | **net_total** | net/趟 | 契約 exit | outcome | 備註 |
|----|----------|--:|------------:|--------------:|-------:|-----------|---------|:----------:|
| **018** GUDT | gk1_rt0p4…tp3 | 53 | 438.9 | **+173.9** | +3.28 | atr_trail_skew_900s | `gudt_no_skew_champion` | near-miss 標竿 |
| **006** VSF | k=2.5 barrier | 105 | 687.2 | **+162.2** | +1.55 | atr_barrier_180s | thesis_c_v21_train_no_go | 部分（事後 k） |
| **006** VSF | k=2.5 Short only | 51 | 554.4 | **+299.4** | +5.87 | atr_barrier_180s | 同上 | 部分（方向切片） |
| **014** MVHP | hm10… | 7 | — | **+133.0** | +19.0 | atr_barrier | `mvhp_fingerprint_fail` | 樣本稀 |
| **016** GDC | grid best | 79 | — | −55.4 | −0.70 | atr_barrier_900s | fingerprint_pass_g1_fail | 否 |
| **019** SFBT | fingerprint | 229 | — | **−871.5** | −3.81 | fvg_mid_trail | fingerprint_pass_g1_fail | 否 |
| **015** FRP | sl3… | 211 | — | −986.4 | −4.67 | atr_barrier | fingerprint_fail | 否 |
| **013** STF | ap10… | 67 | — | −493.0 | −7.36 | atr_barrier | fingerprint_fail | 否 |
| **011** SCB | rm30 | 46 | — | −138.5 | −3.01 | atr_barrier_1200s | train 負 | 否 |
| **017** CFA | — | 0 | 0 | 0 | — | — | spec_anchor_mismatch | 否（設計錯） |
| **009** ORB | 2025 複驗 | — | — | **全 param net 負** | — | atr_barrier | MVPClosed | 否 |
| **010** VTP | rcy10 | 3 | — | +41.9 | +13.95 | atr_barrier_1200s | n≪30 | 樣本稀 |

**Legacy（非 2025 train）**

| FT | 區間 | net_total | 備註 |
|----|------|----------:|------|
| 004 MC | 2026-04 entered | −995.3 | timeout cohort armed_tick **+621** = 錯誤 cohort |
| 005 TC | 2026-04 timeout_tick | −74.8 | armed_tick on timeout **+2579** = 非 thesis |
| 008 SB | 01–04 某子集 | +2873 | **close_1h 切片**；全 cohort 最佳 net **−0.60** |

**關係**：`net_mean > 0` ⟺ `net_total > 0`（同批交易）。爭點在 **disqualify 規則** 與 **exit 契約選擇**，非 mean vs total 公式。

---

## C. 五個假陽性陷阱（流程 MUST 擋）

1. **`horizon_1800s`** — FT-006 k=2.5 net_total **+2422**（無 barrier stop）→ 不可執行  
2. **錯誤 cohort** — FT-004/005 若用 armed_tick on timeout 子集 → 巨額正 total  
3. **子集 bucket** — FT-008 close_1h only → 全 cohort 仍負  
4. **fingerprint ≠ 契約** — FT-019 W900 med +1、契約 gross 1.19  
5. **事後 k / 方向切片** — FT-006 k=2.5、Short only（凍結 k=2.0）

---

## D. 五個假陰性候選（near-miss）

| FT | 現象 | 死因 | 提案 v1.7 處置 |
|----|------|------|----------------|
| **018** | train net +173.9, G1/G2 過 | skew payoff 2.03<2.5 | Class Appeal · near_miss registry |
| **014** | net +133, n=7 | G3 n<30 | `sample_sparse` · 新 thesis 放寬觸發 |
| **006** k=2.5 | net +162, mean 正 | median DQ；非 pre-register k | 登錄 · 禁止救屍 |
| **009** | legacy 01–04 過 | 2025 全負 | 正確殺；教訓=子集幻覺 |
| **016** entry | W30 +13 | exit kills | reuse entry P0（GUDT 已試） |

---

## E. 請資深 TXF 明確裁決的 6 題

1. **FT-018**：train G1/G2 過、net_total +173.9，僅 skew payoff 未過 — **錯殺** 還是 **正確保守**？是否允許 `thesis_class` 申訴 → `mean_robust` **只讀複審**（禁 grid）？  
2. **G1 gross>5**：低頻厚尾（n≈50、win≈49%、gross med=0）是否過嚴？改 **gross_total 年化** 或 **雙軌**（mean_robust=mean，skew=total+tail）？  
3. **Fingerprint 0c-1**：W900 正但契約 gross<2 — 是否 **合併 J1+J2 單關卡**（契約 gross_mean≥3）？  
4. **MVPClosed 同標籤** — 要幾級 `outcome_class`？人類 15 分鐘能否分辨？  
5. **Near-miss registry**：train net_total>0 未過次級 gate — **封存** 還是 **closure_review**（TXF 簽名、禁 tune）？  
6. **Exit-led 分叉**：GDC→GUDT 後 valid 仍負 — **禁止第三 exit FT**？

---

## F. 建議 TXF 輸出格式

請依 role 檔 **五段式**：

1. 關鍵分析  
2. 風險評估  
3. 建議行動或設計考量（對 v1.7 逐條）  
4. 協作備註  
5. 免責與人類決策權  

並 **逐題回答 §E 六題**（Approve / Reject / Revise + 理由）。

### 建議 Cursor 指令

```text
讀 docs/features/ai-backtest-tuning/META_REVIEW_BRIEF.md +
ALPHA_RESEARCH_PLAYBOOK.md + HOLDOUT_CONTRACT_v2.md +
workspaces/CORPSE_ATLAS.md §FT-018。
任務：對 Playbook 流程本身做 meta-review。
重點：錯殺風險、FT-018、gate 指標（mean vs total、net_total 帳面）。
輸出：senior-trading-professional 五段式 + §E 六題逐題裁決。
```

---

## §TXF Response

> **狀態**：`TXF-Responded` — 2026-06-30 · 資深 TXF meta-review（`/senior-trading-professional`）

**總裁決（元問題 A）**：Playbook v1.6/v1.7 **沒有系統性誤殺真信號**；全 FT-004+ holdout 未過主因是 **valid/holdout  regime 不支撐**，不是 G1/G2 算錯。v1.7 已補上的 `net_total` 第一頁、`outcome_class` 分層、Joint Fingerprint J2、Class Appeal 路徑——**方向正確，應落地**。FT-018 是流程改進的 **標竿 near-miss**，不是應復活的 champion。

---

### 1. 關鍵分析

**Playbook 做對的事（必留）**

| 規則 | 理由 |
|------|------|
| G1 gross/趟 >5 · G2 net/趟 >0 | 5 點摩擦下，典型單筆仍須有緩衝；帳面表顯示多數 FT 全 param 負，門檻沒有「殺光」 |
| §C 五陷阱擋板 | `horizon_*`、錯 cohort、子集切片、fingerprint≠契約、事後 k——每一條都有屍體證據 |
| 2025 全年 train 封印 | FT-009 legacy 01–04 過、2025 全負——切片幻覺有抓到 |
| skew 賽道 G-SK1–SK5 | 取代 mean_robust median 一票否決，是對厚尾 thesis 的正確讓步 |
| valid net≤0 禁 holdout | FT-018 valid n=11、net/趟 −2.03——train 帳面正不足以推翻 |
| exit-led **一輪** + 禁第三 exit | GDC→GUDT 已證 entry P0 可 reuse、execution 仍負 |

**審計質疑裡「部分成立」的項**

- **net_total 正仍 MVPClosed**：敘事問題（v2.3 已修），不是規則錯。死因須看 `outcome_class`，不能只看 umbrella。
- **FT-018 疑似錯殺**：train +173.9 值得登錄，但 **skew payoff 2.03 < 2.5**、**gross med=0**、**valid 全負**——這是「帳面勉強正、形狀不像厚尾、樣外失效」，不是被 G1 誤殺。
- **MVPClosed 難分辨**：v1.7 `OUTCOME_REGISTRY` L0–L4 已解；人類 15 分鐘可判若 `gate_report` 第一頁強制 `outcome_class` + `closure_review` 欄。

**FT-018 只讀 mean_robust 複審（已執行 · `gudt-baseline/gate_report.md`）**

| 檢查 | 結果 |
|------|------|
| G1/G2/G3 | 通過 |
| §3.1 gross_median ≤ −5 | **未觸**（med=0） |
| §3.1 方向 / 單向 80% | long-only 預先封印 · 通過 |
| skew G-SK1 payoff | **2.03 < 2.5** ← 唯一 skew 死因 |
| valid 2026 Q1 | net/趟 **−2.03** · holdout_blocked |

**結論**：skew 賽道 **正確保守**；mean_robust 複審技術上可過次級 DQ，但 **不改 MVPClosed**——valid regime fail + exit_gap ~23 才是交易員視角的終判。

---

### 2. 風險評估

**模型 / 回測**

- 低頻 n≈50：mean 正、median≤0 是 **常態**，不是 bug；用 skew 次級門檻（payoff、tail、G-SK5）比放寬 G1 安全。
- `gross_total` 年化或 total-only 冠軍選取 → **高切片 / 厚尾集中風險**（§C 陷阱 3、5）。
- FT-006 k=2.5、Short only 事後切片：**不得**當 pre-register 證據。

**執行**

- FT-018 exit_gap ~23：stop-less W900 med +8 vs 契約 net +3.3/趟——**執行層吃掉過半 edge**；再開第三 exit 是 tune 屍體參數。
- Fingerprint W900 正、契約 gross<3（FT-019）：grid 假希望 → Joint J2 必須擋在 0c-1。

**制度 / 流程**

- 無 near-miss 登錄 → 人類重複踩 GDC entry、不同 exit 的迴圈。
- `spec_anchor_mismatch` 與 `no_skew_champion` 混談 → 浪費設計審閱週期（L0 vs L2 已拆）。

---

### 3. 建議行動或設計考量（v1.7 逐條）

| 項目 | 裁決 | v1.7 動作 |
|------|------|-----------|
| G1 gross>5 | **必留** | 不改門檻；skew/mean_robust 共用 |
| G1 改 gross_total 年化 | **Reject** | 僅 `gate_report` 診斷列，不作冠軍選取 |
| 雙軌 thesis_class | **Approve**（已落地） | mean_robust=§3.1 median DQ；skew=§3.2 G-SK |
| Joint Fingerprint J1+J2 | **Approve**（Playbook §3.1c） | J2 契約 gross_mean≥3 · outcome `fingerprint_contract_mismatch` |
| outcome_class L0–L4 | **Approve** | `gate_report` §Decision 第一列強制 |
| Class Appeal §2.3 | **Approve** | 觸發條件照 HOLDOUT v2.3；**通過 ≠ 開 plugin** |
| Near-miss registry | **Approve** closure_review | TXF+Tim 簽名 · 禁 tune · 登 `NEAR_MISS_REGISTRY.md` |
| 禁第三 exit（同 entry P0） | **Approve** | GDC/GUDT 線封頂；新進場機制才准新 FT |
| skew payoff_min 2.5 | **必留** | FT-018 的 2.03 不足以 Revise 下調 |
| train net_total 第一頁 | **Approve**（v2.3 已 MUST） | 維持 `summarize_alpha_train` |

---

### 4. 協作備註

| 角色 | 動作 |
|------|------|
| **工程 Agent** | 確保 `build_gate_summary()` 產 `outcome_class` + warnings；舊 `gate_report` 補登 FT-018 `closure_review: eligible` |
| **Tim（人類）** | 簽核 FT-018 near-miss 一列；**不**批准第三 exit 或 skew payoff 下調 |
| **Daily Reviewer** | 週報引用 `OUTCOME_REGISTRY` 統計 L0/L1/L2 分布，避免「又一個 MVPClosed」無上下文 |
| **Ops** | 無 Pilot 動作；UAT 維持 `strategy-vwap-momentum` |

---

### 5. 免責與人類決策權

本回覆為 **Alpha 0-design / Phase 0 流程** 設計意見，非投資建議。所有 holdout 封印、plugin 開工、Pilot Go/No-Go 決策權在 **人類**。即使 Class Appeal 通過 mean_robust 次級檢查，**valid 負、holdout 未跑** 仍不得宣稱 Live Ready。

---

## §E 六題逐題裁決

### E1 — FT-018：skew payoff 未過是錯殺還是正確保守？Class Appeal？

| | |
|---|---|
| **裁決** | **Revise**（流程）+ skew 賽道 **Reject 錯殺論** |
| **理由** | train net +173.9、G1/G2 過，值得 near-miss；但 payoff **2.03<2.5**、gross med **0**、win≈49%——形狀是「勉強正的均值策略」，不是 pre-register 的厚尾 skew。valid Q1 net/趟 **−2.03** 支持保守結案。 |
| **Class Appeal** | **Approve 機制** · **Reject 改結案**：只讀 mean_robust 複審 **已做且通過次級 DQ**；結論仍 **MVPClosed**，登 near-miss，`closure_review_passed_mean_track` 可標，**不開 plugin、不跑 holdout**。 |

### E2 — G1 gross>5 對低頻厚尾是否過嚴？改年化或雙軌？

| | |
|---|---|
| **裁決** | **Approve 必留 G1** · **Reject gross_total 年化作主判** · **Approve 雙軌**（已實作） |
| **理由** | FT-018 死在 **G-SK1**，不是 G1（gross/趟 8.28）。低頻厚尾的讓步應在 §3.2（payoff、tail、G-SK5），不是放寬 G1。total 年化易被少數大贏家支配。 |

### E3 — Fingerprint 0c-1：合併 J1+J2（契約 gross_mean≥3）？

| | |
|---|---|
| **裁決** | **Approve** |
| **理由** | FT-019：W900 med +1、契約 gross 1.19——J1 單獨通過會浪費整段 grid。J2≥3 是診斷下限；G1>5 仍在 0c-2。未過 → `fingerprint_contract_mismatch`，**禁止 grid**。 |

### E4 — MVPClosed 要幾級 outcome_class？人類 15 分鐘能否分辨？

| | |
|---|---|
| **裁決** | **Approve** L0–L4（`OUTCOME_REGISTRY.md`） |
| **理由** | 四層足夠：`design_error` / `no_gross_edge`+`direction_falsified` / `execution_gap`+`skew_profile_fail` / `valid_regime_fail`+`near_miss`。15 分鐘可判若 §Decision 固定三行：`outcome_class` · 細碼 · `closure_review Y/N`。 |

### E5 — Near-miss registry：封存還是 closure_review？

| | |
|---|---|
| **裁決** | **Approve closure_review**（TXF 簽名 · 禁 tune） |
| **理由** | 純封存會丟掉 FT-018/014/006 的 entry 資產。條件：train `net_total>0` + phase0 G1/G2 過 + 次級未過；登錄後僅只讀複審/新 thesis 參考，**禁止**依 registry 重跑 grid。 |

### E6 — Exit-led 分叉：GDC→GUDT 後 valid 仍負，禁第三 exit FT？

| | |
|---|---|
| **裁決** | **Approve 禁止第三 exit** |
| **理由** | 同一 GDC entry P0 已跑 barrier_900s → trail_skew_900s；valid 仍負。再開 exit 是 post-hoc rescue，違反 Playbook §4。GDC entry 可 **reuse 於新進場 thesis**（不同觸發），不可再換 exit 變體。 |

---

**簽核**：資深 TXF meta-review · 2026-06-30

---

## 參考

- [ALPHA_RESEARCH_PLAYBOOK.md](ALPHA_RESEARCH_PLAYBOOK.md) v1.6.1  
- [HOLDOUT_CONTRACT_v2.md](HOLDOUT_CONTRACT_v2.md) v2.2.1  
- [CORPSE_ATLAS.md](../../../workspaces/CORPSE_ATLAS.md)  
- [gudt-baseline/gate_report.md](../../../workspaces/gudt-baseline/gate_report.md)
