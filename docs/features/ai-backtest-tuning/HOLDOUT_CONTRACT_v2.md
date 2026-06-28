---
id: HOLDOUT-v2
slug: holdout-contract
version: 2.2.1
status: Active
opened: 2026-06-28
revised: 2026-06-28
supersedes: FT-003 SPEC §4.1（單月 holdout 隱含慣例）
applies_to: FT-004+ counterfactual · plugin baseline · Pilot-prep thesis
owner: human+agent
---

# Holdout 契約 v2.2.1

> **SSOT**：策略 thesis（`docs/features/<slug>/`）的 **train / valid / holdout / confirm** 切分與 **No-Go 門檻**。  
> FT-003 grid 競賽仍用 [`SPEC.md`](SPEC.md) §4 + [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)「2026 競賽切分」；**新 thesis（FT-011+）MUST 用 §2.1**。

**v2.1 動機**：FT-006/009 單月 holdout 樣本過少；FT-009 冠軍 **Short 厚尾 + median 負**。**2025 全年 tick_cache 落地**（247 日）後，train 拉長、holdout 拉成三月。

**v2.2 動機（2026-06-28 · 人類 Tim GO）**：新增 **`thesis_class: skew`** 平行賽道 — 接受 **低頻、median 難看、靠厚尾拉 mean** 的 thesis；以 **payoff ratio / 尾部筆數 / 連虧 / 月 DD** 取代 §3.1 median 一票否決。**不**放寬 holdout 封印、**不**自動復活 MVPClosed FT（§11）。

**v2.2.1 動機（2026-06-28 · 資深交易員 review Revise）**：**G-SK5** 尾部集中度防 lottery skew；**skew valid 硬擋** 禁止 overfit 進 holdout；摩擦 **@7** disqualify；**G-SK3** 增列連虧點數上限。

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
# 全庫 audit 非每次 CF；見 workspaces/CACHE_AUDIT.md
python -m storage.cache_audit --code TMFR1 --from-date YYYY-MM-DD --to-date YYYY-MM-DD  # backfill 後增量
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

## 2.2 Thesis class（**v2.2 · FT-013+ 必選**）

| `thesis_class` | 適用 | Gate SSOT | 預設 |
|----------------|------|-----------|------|
| **`mean_robust`** | 中高頻、典型一筆也要扛摩擦 | §3.1 + G3 **n≥30** | **是**（未宣告則此） |
| **`skew`** | 低頻、可接受 win rate 低、靠厚尾 | §3.2 + G3S **n≥15** | 須 THESIS_BRIEF **§E.3** + queue **`human-approved`** 明示 |

**Skew 准入（MUST 全滿）**

- [ ] 進場 **非** Playbook §4 **VWAP fade 整族**、**非**已 MVPClosed 進場機制換皮
- [ ] 出場 **MUST** `k_sl × ATR` 且 **k_sl ≥ 0.5**（禁止 skew 賽道用固定 6 點當主 stop）
- [ ] Pre-register：`payoff_ratio_min`、`max_consecutive_losses`、`worst_month_net_pts`、`tail_gross_min_pts`（預設 15）
- [ ] SPEC 頂部 YAML：`thesis_class: skew`

**Skew 禁入**：mean-reversion fade · 無新 FT 編號的 ORB/SCB 變體 · 僅為「救屍」重跑舊 CF。

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
| FT-006 | **MVPClosed** | valid 過 / 05 holdout 負 / **v2.1 train 2025 未過**（`thesis_c_v21_train_no_go`） |

新 thesis **不得** 宣稱「沿 v2.0 通過」除非明示 legacy 複驗 run id。

---

## 3. Phase 0 Gate（Train 窗 — v2.1+ = 2025 全年）

### 3.0 共用（`mean_robust` **與** `skew`）

| ID | 條件 | 未過 |
|----|------|------|
| **G1** | train gross/趟 **> 5** | MVPClosed |
| **G2** | train net/趟 **> 0**（摩擦 5 點） | MVPClosed |
| **G4** | train QSL **< 25%** | 診斷；`hard_stop_atr_k` **一次**重跑 |
| **G5** | train 無單月 net/趟 **< −2** | 不穩標記（skew 改看 **G-SK4** 月 DD） |

| Class | 樣本 | 未過 |
|-------|------|------|
| **mean_robust** | **G3** train **n ≥ 30** | MVPClosed |
| **skew** | **G3S** train **n ≥ 15** | MVPClosed |

### 3.1 冠軍選取 — `mean_robust`（MUST · 預設）

1. **net/趟最高**（平手 → n 較大）
2. **方向拆解 MUST**：Long / Short 分欄
3. **Disqualify**（任一）：
   - `gross_median ≤ −5`
   - 單一方向貢獻 **> 80%** gross PnL
   - 任一方向 train net/趟 **< −3**

無合格冠軍 → **`no_robust_champion`**，不進 Holdout。

### 3.2 冠軍選取 — `skew`（v2.2 · 厚尾賽道）

**取代 §3.1 median 紅旗**；方向拆解仍 MUST。

| ID | 條件 | 未過 |
|----|------|------|
| **G-SK1** | `payoff_ratio` = mean(gross\|win) / \|mean(gross\|loss)\| **≥** pre-register `payoff_ratio_min`（預設 **2.5**） | disqualify |
| **G-SK2** | **tail_count** ≥ 5：gross ≥ pre-register `tail_gross_min_pts`（預設 **15**） | disqualify |
| **G-SK3** | **max_consecutive_losses**（net≤0 連續筆）≤ pre-register（預設 **10**） | disqualify |
| **G-SK3b** | **max_consecutive_loss_pts**（同上連虧段合計 net 點數）≤ pre-register（預設 **150**） | disqualify |
| **G-SK4** | **worst_calendar_month** 合計 net **>** pre-register `worst_month_net_pts`（預設 **−120**） | disqualify |
| **G-SK5** | **top3_win_gross_share** = 前 3 大 gross 贏家合計 / 總 gross **≤ 0.65** | disqualify |

**§3.2 Disqualify（仍適用）**

- 單一方向貢獻 **> 80%** gross PnL — **除非** SPEC 事前 **Long-only** 或 **Short-only** 且 queue 已註明
- 任一方向 train net/趟 **< −3**
- `gross_median ≤ −5` **不**自動 disqualify（若 G-SK1–SK5 全過）
- **摩擦 @7 點**：`net/趟 @ friction=7` **≤ 0** → disqualify（skew 附錄 MUST 計算）

**gate_report MUST 附錄（skew only）**

- win_rate · payoff_ratio · tail_count · max_consecutive_losses · **max_consecutive_loss_pts** · worst_month_net · **top3_win_gross_share**
- **摩擦敏感度**：net/趟 @ 摩擦 **3 / 5 / 7** 點（主判仍 5；**@7 ≤ 0 → disqualify**）
- payoff 分布 p10/p50/p90 gross
- **post_entry** W30 stop-less median（Corpse Atlas 格式一行；**不**推翻 G1–G2）

無合格冠軍 → **`no_skew_champion`**，不進 Holdout。

---

## 4. Valid（v2.1 = 2026 Q1）

| 角色 | `mean_robust` | `skew` |
|------|---------------|--------|
| 主判 | **不作** Phase 0 過關依據 | 同左 |
| 紅旗 | train 過但 valid net ≤ 0 → **`overfit_suspect`** | 同左 |
| **硬擋（v2.2.1）** | 記錄於 gate_report；**可**進 holdout 封印（人類知悉風險） | valid net ≤ 0 → **`overfit_suspect` · 不得進 holdout 封印** |
| 動作 | gate_report **MUST** 記 valid 對照 | 同左 + 附錄標 `holdout_blocked_overfit` |

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

#### 5.2a `mean_robust`（預設）

| ID | 條件 |
|----|------|
| **H1** | holdout gross/趟 **> 5** |
| **H2** | holdout net/趟 **> 0** |
| **H3** | holdout n ≥ **30**（中/高頻三月）或 ≥ **20**（低頻三月） |
| **H4** | holdout gross_median **> −5** |
| **H5** | Long/Short 不得雙邊皆爛（一邊 < −5/趟 且另一邊 < 0） |

#### 5.2b `skew`（v2.2）

| ID | 條件 |
|----|------|
| **H1–H2** | 同 5.2a |
| **H3S** | holdout n ≥ **12**（三月合併）且 holdout **合計 net PnL > 0** |
| **H4S** | G-SK1 成立（holdout payoff_ratio ≥ pre-register）且 **tail_count ≥ 3**（holdout） |
| **H5** | 同 5.2a |
| **—** | holdout gross_median **不**作硬否決（改看 H4S） |

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

## 8. gate_report 模板（v2.2）

```markdown
## Thesis class
mean_robust | skew

## Train（2025 全年）
| param | n | gross | net | gross_median | Long net | Short net |

## Skew 附錄（僅 skew）
payoff_ratio · tail_count · max_consecutive_losses · worst_month_net · friction 3/5/7

## Valid（2026 Q1）
（對照表）

## Holdout（2026 Q2 · 04–06）
| param | n | gross | net | gross_median | 判定 |

## 冠軍資格
- [ ] G1–G2 · [ ] G3 or G3S · [ ] §3.1 or §3.2 · [ ] H1–H5 or H3S/H4S

## §Decision
```

---

## 9. 版本對照

| 版本 | Train | Valid | Holdout | 適用 |
|------|-------|-------|---------|------|
| **v2.2.1** | 2025 全年 | 2026 Q1 | 2026 Q2 (04–06) | **FT-013+** · skew + G-SK5 / valid 硬擋 |
| **v2.2** | 2025 全年 | 2026 Q1 | 2026 Q2 (04–06) | FT-013 過渡（已被 v2.2.1 取代） |
| **v2.1** | 2025 全年 | 2026 Q1 | 2026 Q2 (04–06) | **FT-011–012** · 僅 `mean_robust` |
| v2.0 | 2026 Q1 | 2026-04 | 2026 05–06 | 文件過渡 |
| legacy | 2026 01–04 合計 | — | 2026-05 | FT-009 Phase 0 |

---

## 11. MVPClosed 屍體政策（v2.2 · MUST NOT 誤解）

| 規則 | 說明 |
|------|------|
| **不自動復活** | 改契約 **≠** 翻案 FT-003～012；既有 `gate_report` 結論封存 |
| **允許重驗** | 僅當 **新 FT 編號** + **新進場機制**（THESIS_BRIEF §C）+ queue **`human-approved`** + 人類明示「skew 重驗」 |
| **預期結果** | FT-009 厚尾 archetype 在 skew 下仍預期 **holdout 否決**（v2.1 已 `holdout_fail_structural`）；重驗是 **確認屍體**，不是救 plugin |
| **Corpse Atlas** | [`CORPSE_ATLAS.md`](../../../workspaces/CORPSE_ATLAS.md) verdict **不**因 v2.2 推翻 |

索引：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §8.2 · [`THESIS_QUEUE.md`](../../../workspaces/THESIS_QUEUE.md)

---

## 10. 實作清單

- [x] [`DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md) 2025 落地檔數
- [x] v2.1 本檔
- [x] **v2.2** `thesis_class: skew` 賽道（§2.2 · §3.2 · §5.2b · §11）
- [x] **v2.2.1** G-SK5 · G-SK3b · skew valid 硬擋 · friction@7 disqualify
- [ ] 通用 CF CLI：`--train-from 2025-01-01` 等預設改 v2.1
- [ ] gate 輸出 skew 附錄（payoff / friction sensitivity）
- [ ] gate 輸出 median / 3.1 disqualify
- [x] FT-009 legacy 封存（不重跑）

---

## 參考

- [`workspaces/DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)
- [`SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §1.1
- [`orb-baseline/gate_report.md`](../../../workspaces/orb-baseline/gate_report.md)
