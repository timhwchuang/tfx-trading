---
id: HOLDOUT-v2
slug: holdout-contract
version: 2.0
status: Active
opened: 2026-06-28
supersedes: FT-003 SPEC §4.1（單月 holdout 隱含慣例）
applies_to: FT-004+ counterfactual · plugin baseline · Pilot-prep thesis
owner: human+agent
---

# Holdout 契約 v2

> **SSOT**：策略 thesis（`docs/features/<slug>/`）的 **valid / holdout / confirm** 切分與 **No-Go 門檻**。  
> FT-003 grid 競賽仍用 [`SPEC.md`](SPEC.md) §4 + [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)；**新 thesis Phase 0+ MUST 對齊本檔**。

**動機**（2026-06-28）：FT-006 / FT-009 單月 holdout（2026-05）樣本過少（ORB n=19）；FT-009 01–04 冠軍 **Short 厚尾 + median 負**，一月 holdout 確認 regime 翻車但 **統計信心不足**。本檔補：**最少月數 / 最少 n / 方向與 median 門檻 / 擴充資料切分**。

---

## 1. 資料時間軸（2025-01 起）

| 區段 | 日曆 | 狀態（2026-06-28） | 用途 |
|------|------|-------------------|------|
| **歷史 WFO** | 2025-01-01～2025-12-31 | 待 backfill | **僅**滾動 WFO / 穩健性報告；**禁止**事後 tune 已封印 thesis |
| **Train** | 2026-01-01～2026-03-31 | tick_cache 就緒 | Phase 0 **主判**（gross/net/n） |
| **Valid** | 2026-04-01～2026-04-30 | 就緒 | 參考 + overfit 探測；**可作** Phase 1 門檻 |
| **Holdout A** | 2026-05-01～2026-05-31 | 就緒（已用於 FT-006/009） | 封印塊 1 |
| **Holdout B** | 2026-06-01～2026-06-30 | **待落地**（UAT tick 壓縮 / backfill） | 封印塊 2 |
| **Confirm** | 2026-07+ | 未來累積 | Paper / shadow；**不得**回頭 tune 2026 H1 參數 |

**Backfill SOP**（2025-01 起）：

```bash
cd apps/trading-app/src
# 收盤後、勿與 live 同時 login
python -m backfilldata date YYYY-MM-DD   # 逐日或批次腳本
python -m storage.cache_audit --code TMFR1
```

落地 2026-06 後更新 [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md) 檔數表。

---

## 2. 標準三段 + 雙塊 Holdout（新 thesis 預設）

```text
2026-01 … 03  →  TRAIN     （主判 G1–G3）
2026-04       →  VALID     （參考；valid net≤0 → overfit suspect）
2026-05 + 06  →  HOLDOUT   （封印至 champion 凍結；合併評估）
2026-07+      →  CONFIRM   （shadow；非 gate）
```

| 區間 | CLI 範例 | 可否依結果 tune |
|------|----------|-----------------|
| Train | `--train-from 2026-01-01 --train-to 2026-03-31` | Phase 0 grid **僅**此區間 |
| Valid | `--valid-from 2026-04-01 --valid-to 2026-04-30` | 診斷 only；**不作**事後換冠軍 |
| Holdout | `--holdout-from 2026-05-01 --holdout-to 2026-06-30` | **否** |

**向後相容**：已跑完 **僅 05** holdout 的 FT（006/009）結論 **保留**；重跑須新 ft 子版本或人類書面「v2 複驗」。

---

## 3. Phase 0 Gate（Train 01–03）

| ID | 條件 | 未過 |
|----|------|------|
| **G1** | train gross/趟 **> 5** | MVPClosed |
| **G2** | train net/趟 **> 0**（摩擦 5 點） | MVPClosed |
| **G3** | train **n ≥ 30** | MVPClosed |
| **G4** | train QSL **< 25%** | 診斷；可調 `hard_stop_atr_k` **一次**重跑 |
| **G5** | train 無單月 net/趟 **< −2** | 不穩標記 |

### 3.1 冠軍選取（v2 新增 — MUST）

在通過 G1–G3 的 param 中，依序：

1. **net/趟最高**（平手 → n 較大）
2. **方向拆解 MUST 產出**：Long / Short 分欄 gross、net、n
3. **拒絕冠軍若**（任一即 **disqualified**，即使 mean 最高）：
   - **Gross_median ≤ −5**（多數單筆結構性虧損；與 FT-009 rm30 median −6 同型）
   - **單一方向貢獻 > 80%** 總 gross PnL（厚尾單邊；FT-009 Short 主導）
   - **任一方向** train net/趟 **< −3**

若無 param 通過 3.1 → Phase 0 標 **`no_robust_champion`**，**不進** Holdout（省時間）。

---

## 4. Valid（2026-04）

| 角色 | 規則 |
|------|------|
| 主判 | **不作** Phase 0 過關依據 |
| 紅旗 | train 過但 valid net ≤ 0 → **`overfit_suspect`**（FT-006/008/009 路徑） |
| 動作 | 可進 Holdout，但 gate_report **MUST** 記 valid 對照表 |

---

## 5. Holdout（v2 核心）

### 5.1 樣本門檻（依策略頻率）

| 類型 | 估計頻率 | Holdout **最少** | 單月可否單獨結案 |
|------|----------|------------------|------------------|
| **高頻** | ≥ 30 筆/月 | **1 個月** 且 n ≥ 30 | 可 |
| **中頻** | 10–30 筆/月 | **2 個月** 合計 n ≥ **30** | 單月僅能標「參考」 |
| **低頻** | < 10 筆/月 | **2 個月** 合計 n ≥ **20** 且兩月 **net 同號** | **否** — 單月不得 MVPClosed |

ORB（~19 筆/月）屬 **中頻邊界**：v2 要求 **05+06 合併** 再判；僅 05 的 No-Go 改為 **「v1 單月紅燈 + v2 待複驗」** 若 06 落地後合併仍負且無結構豁免。

### 5.2 Holdout 通過（MUST 全滿足）

| ID | 條件 |
|----|------|
| **H1** | holdout gross/趟 **> 5** |
| **H2** | holdout net/趟 **> 0** |
| **H3** | holdout **n ≥ 20**（中/低頻兩月合計）或 **n ≥ 30**（高頻單月） |
| **H4** | holdout gross_median **> −5** |
| **H5** | Long / Short holdout net **不得**一邊 **< −5/趟** 且另一邊 **< 0**（雙邊皆爛） |

### 5.3 Holdout 否決（任一即 No-Go UAT）

| 情境 | 決策 |
|------|------|
| H1–H3 未過 | **MVPClosed** |
| H4–H5 未過但 H1–H3 過 | **Pilot-prep 凍結**；須 WFO 或 Confirm，**不** UAT |
| train 有 3.1 紅旗 + holdout 負 | **MVPClosed**（無需爭論樣本量） |
| 事後改 param（如 FT-009 rm15） | **禁止** |

### 5.4 單月 holdout 的定位

| 結果 | 標記 |
|------|------|
| 單月 net 負 + train 曾有 3.1 紅旗 | **`holdout_fail_structural`** — 可結案 |
| 單月 net 略負 + train 乾淨 + n < 20 | **`holdout_inconclusive`** — **不得**單獨 MVPClosed；等次月或 WFO |
| 單月 net 正 + n 小 | **`holdout_pass_weak`** — 不進 UAT；須 H 全過或 06 合併 |

---

## 6. 滾動 WFO（2025 歷史 + 可選 Phase 6）

**Gate**：Holdout H1–H3 通過後才跑（或 MVPClosed thesis 不做）。

| 項目 | 規則 |
|------|------|
| 資料 | 2025-01 起 backfill；**每 fold 訓練窗不得包含該 fold 測試月** |
| 最少 folds | **4**（建議季滾：2025 Q1→Q2→Q3→Q4 測試） |
| 通過 | **≥ 3/4** fold 的 test net/趟 **> 0** |
| 產物 | `workspaces/<slug>-baseline/reports/wfo_summary.json` |

WFO **不能取代** 2026 holdout；兩者皆過才可標 **Pilot-prep Go**。

---

## 7. Confirm（2026-07+ / Paper）

| 項目 | 規則 |
|------|------|
| 目的 | 執行層（fill、cancel、slippage）非再 tune 進場 |
| 時長 | ≥ **3 週** 或 ≥ **15** 筆 round-trip |
| 通過 | `compare_fill_audits` net 衰退 **< 25%** vs plugin baseline |
| 失敗 | 凍結 Pilot；**不回** 2026 H1 tune |

---

## 8. gate_report 必填欄位（模板）

```markdown
## Train（01–03）
| param | n | gross | net | gross_median | Long net | Short net |

## Valid（04）
（對照表）

## Holdout（05–06 合計）
| param | n | gross | net | gross_median | 判定 |

## v2 冠軍資格
- [ ] G1–G3
- [ ] 3.1 無 disqualify
- [ ] H1–H5

## §Decision
```

---

## 9. 與舊 FT 對照

| FT | v1 結論 | v2 備註 |
|----|---------|---------|
| FT-006 | valid 過 / 05 holdout 負 | 單月紅燈；可選 05+06 複驗（新 run id） |
| FT-009 | 01–04 過 / 05 負 / Short 厚尾 | **holdout_fail_structural**；06 合併僅作存檔 |
| FT-010 | Phase 0 n≪30 | 不適用 holdout |

---

## 10. 實作清單（Agent）

- [x] 更新 [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)（2025 backfill + 2026-06 待落地）
- [x] holdout CLI：`run_cf_holdout.py --holdout-v2` · `ft009_run_baseline.py --holdout-v2`（05–06 合併）
- [ ] 通用 `--holdout-from` / `--holdout-to`（全 counterfactual CLI）
- [ ] `_evaluate_phase0_gate` 系列：輸出 `gross_median`、方向拆解、3.1 disqualify
- [x] FT-009 SPEC / gate_report 連結本檔 §2–§5

---

## 參考

- 資料切分：[`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)
- 摩擦：[`workspaces/SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §3
- FT-009 教訓：[`workspaces/orb-baseline/gate_report.md`](../../../workspaces/orb-baseline/gate_report.md)
- 波動敘事：[`workspaces/VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md)
