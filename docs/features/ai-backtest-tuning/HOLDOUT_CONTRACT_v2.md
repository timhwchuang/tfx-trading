---
id: HOLDOUT-v2
slug: holdout-contract
version: 2.1
status: Active
opened: 2026-06-28
supersedes: FT-003 SPEC §4.1（單月 holdout 隱含慣例）
applies_to: FT-004+ counterfactual · plugin baseline · Pilot-prep thesis
owner: human+agent
---

# Holdout 契約 v2.1

> **SSOT**：策略 thesis（`docs/features/<slug>/`）的 **train / valid / holdout / confirm** 切分與 **No-Go 門檻**。  
> FT-003 grid 競賽仍用 [`SPEC.md`](SPEC.md) §4 + [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)「2026 競賽切分」；**新 thesis（FT-011+）MUST 用 §2.1**。

**動機**：FT-006/009 單月 holdout 樣本過少；FT-009 冠軍 **Short 厚尾 + median 負**。**2025 全年 tick_cache 落地**（247 日）後，v2.1 將 **train 拉長、holdout 拉成三月**，低頻 thesis 較易過 G3。

---

## 1. 資料時間軸（2025-01 起）

| 區段 | 日曆 | 狀態（2026-06-28） | 用途 |
|------|------|-------------------|------|
| **Train** | **2025-01-01～2025-12-31** | ✅ **247 日** | v2.1 Phase 0 **主判** |
| **Valid** | **2026-01-01～2026-03-31** | ✅ 54 日 | overfit 探測 |
| **Holdout** | **2026-04-01～2026-06-30** | 04–05 ✅ · **06 待落地** | 封印（**三月合併**） |
| **Confirm** | **2026-07-01～** | 🔲 UAT 累積 | Paper / shadow |
| **Legacy train** | 2026-01～03 | ✅ | **僅** v2.0 已結案 FT 對照 |

檔數 SSOT：[`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)。

```bash
cd apps/trading-app/src
python -m storage.cache_audit --code TMFR1   # sweep / CF 前
```

---

## 2.1 標準切分（**新 thesis 預設 · FT-011+**）

```text
2025 全年      →  TRAIN      （主判 G1–G3；~247 交易日）
2026-01 … 03   →  VALID      （近期 regime；net≤0 → overfit suspect）
2026-04 … 06   →  HOLDOUT    （封印；三月合併評估）
2026-07+       →  CONFIRM    （shadow）
```

| 區間 | CLI 範例 | 可否依結果 tune |
|------|----------|-----------------|
| Train | `--train-from 2025-01-01 --train-to 2025-12-31` | Phase 0 grid **僅**此區間 |
| Valid | `--valid-from 2026-01-01 --valid-to 2026-03-31` | 診斷 only |
| Holdout | `--holdout-from 2026-04-01 --holdout-to 2026-06-30` | **否** |

**禁止**：`2025 train + 2026-01~03` 合併 tune；`2025+2026` 全段選參再假裝 holdout。

---

## 2.0 Legacy（v2.0 — 已結案 FT 封存）

適用：**FT-006 / 009 / 010** 等已寫入 gate_report 者；**結論不重跑、不換參**。

```text
2026-01 … 03  →  TRAIN
2026-04       →  VALID
2026-05 (+06) →  HOLDOUT   （FT-006/009 僅 05 封印）
```

| FT | 結論 | 備註 |
|----|------|------|
| FT-009 | MVPClosed | 01–04 過 / 05 holdout 負；`holdout_fail_structural` |
| FT-010 | MVPClosed | 01–03 n≪30 |
| FT-006 | Holdout 未過 | valid 過 / 05 負 |

新 thesis **不得** 宣稱「沿 v2.0 通過」除非明示 legacy 複驗 run id。

---

## 3. Phase 0 Gate（Train 窗 — v2.1 = 2025 全年）

| ID | 條件 | 未過 |
|----|------|------|
| **G1** | train gross/趟 **> 5** | MVPClosed |
| **G2** | train net/趟 **> 0**（摩擦 5 點） | MVPClosed |
| **G3** | train **n ≥ 30** | MVPClosed |
| **G4** | train QSL **< 25%** | 診斷；`hard_stop_atr_k` **一次**重跑 |
| **G5** | train 無單月 net/趟 **< −2** | 不穩標記 |

### 3.1 冠軍選取（MUST）

1. **net/趟最高**（平手 → n 較大）
2. **方向拆解 MUST**：Long / Short 分欄
3. **Disqualify**（任一）：
   - `gross_median ≤ −5`
   - 單一方向貢獻 **> 80%** gross PnL
   - 任一方向 train net/趟 **< −3**

無合格冠軍 → **`no_robust_champion`**，不進 Holdout。

---

## 4. Valid（v2.1 = 2026 Q1）

| 角色 | 規則 |
|------|------|
| 主判 | **不作** Phase 0 過關依據 |
| 紅旗 | train 過但 valid net ≤ 0 → **`overfit_suspect`** |
| 動作 | gate_report **MUST** 記 valid 對照 |

---

## 5. Holdout（v2.1 = 2026 Q2 · 04–06）

### 5.1 樣本門檻

| 類型 | 估計頻率 | Holdout 窗 | 最少 n |
|------|----------|------------|--------|
| **高頻** | ≥ 30 筆/月 | **1 個月** 可 | **30** |
| **中頻** | 10–30 筆/月 | **三月合併**（v2.1 預設） | **30** |
| **低頻** | < 10 筆/月 | **三月合併** | **20** 且三月 net **同號** |

v2.1 預設 **三月 holdout**（04–06）→ 中頻 ORB 類 ~40–60 交易日，較單月 05 可靠。

**06 未落地時**：可先跑 04–05 標 **`holdout_partial`**（不作 MVPClosed 主因）；06 補齊後 **一次** 合併重判。

### 5.2 通過（MUST 全滿足）

| ID | 條件 |
|----|------|
| **H1** | holdout gross/趟 **> 5** |
| **H2** | holdout net/趟 **> 0** |
| **H3** | holdout n ≥ **30**（中/高頻三月）或 ≥ **20**（低頻三月） |
| **H4** | holdout gross_median **> −5** |
| **H5** | Long/Short 不得雙邊皆爛（一邊 < −5/趟 且另一邊 < 0） |

### 5.3 否決

| 情境 | 決策 |
|------|------|
| H1–H3 未過 | **MVPClosed** |
| H4–H5 未過、H1–H3 過 | **Pilot-prep 凍結** |
| 3.1 紅旗 + holdout 負 | **MVPClosed**（不論 n） |
| 事後換 param | **禁止** |

### 5.4 單月 holdout（legacy / 參考）

| 結果 | 標記 |
|------|------|
| 結構紅旗 + 單月負 | `holdout_fail_structural` |
| 乾淨 train + 單月負 + n 小 | `holdout_inconclusive` |
| 單月正 + n 小 | `holdout_pass_weak` |

---

## 6. 滾動 WFO（2025 季滾 · 穩健性附錄）

**Gate**：Holdout H1–H3 通過後（MVPClosed 不做）。

| 項目 | 規則 |
|------|------|
| 資料 | **2025 年內**季滾（與 v2.1 train 同池但 **fold 內不得 tune 後看 test**） |
| Folds | **4**（Q1→Q2→Q3→Q4 各測一季） |
| 通過 | **≥ 3/4** fold test net/趟 **> 0** |
| 與 train 關係 | WFO 用 **凍結冠軍 param** 重播；**不是**第二輪 grid |

WFO **不取代** 2026 Q2 holdout。

---

## 7. Confirm（2026-07+）

| 項目 | 規則 |
|------|------|
| 目的 | fill / slippage；**非** tune 進場 |
| 時長 | ≥ **3 週** 或 ≥ **15** round-trip |
| 通過 | `compare_fill_audits` net 衰退 **< 25%** vs baseline |

---

## 8. gate_report 模板（v2.1）

```markdown
## Train（2025 全年）
| param | n | gross | net | gross_median | Long net | Short net |

## Valid（2026 Q1）
（對照表）

## Holdout（2026 Q2 · 04–06）
| param | n | gross | net | gross_median | 判定 |

## 冠軍資格
- [ ] G1–G3 · [ ] 3.1 · [ ] H1–H5

## §Decision
```

---

## 9. 版本對照

| 版本 | Train | Valid | Holdout | 適用 |
|------|-------|-------|---------|------|
| **v2.1** | 2025 全年 | 2026 Q1 | 2026 Q2 (04–06) | **FT-011+** |
| v2.0 | 2026 Q1 | 2026-04 | 2026 05–06 | 文件過渡 |
| legacy | 2026 01–04 合計 | — | 2026-05 | FT-009 Phase 0 |

---

## 10. 實作清單

- [x] [`DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md) 2025 落地檔數
- [x] v2.1 本檔
- [ ] 通用 CF CLI：`--train-from 2025-01-01` 等預設改 v2.1
- [ ] gate 輸出 median / 3.1 disqualify
- [x] FT-009 legacy 封存（不重跑）

---

## 參考

- [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)
- [`SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §1.1
- [`orb-baseline/gate_report.md`](../../../workspaces/orb-baseline/gate_report.md)
