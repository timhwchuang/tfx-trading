# 資料切分 SSOT（tick_cache · TMFR1）

> **策略 thesis（FT-004+）**：日期角色與 holdout 門檻見 **[`HOLDOUT_CONTRACT_v2.md`](../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)**。  
> **FT-003 grid 競賽**：下表「2026 競賽切分」仍有效；與 v2 **並行**（競賽未廢除）。

## 涵蓋範圍（目標）

| 區段 | 日曆 | 狀態 | 用途 |
|------|------|------|------|
| **歷史 WFO** | **2025-01-01～2025-12-31** | 🔲 待 backfill | 滾動 WFO only（見 HOLDOUT v2 §6） |
| **Train** | 2026-01-01～2026-03-31 | ✅ | Phase 0 主判 |
| **Valid** | 2026-04-01～2026-04-30 | ✅ | 參考 / overfit 探測 |
| **Holdout** | 2026-05-01～**2026-06-30** | 05 ✅ · **06 待落地** | 封印（v2：**兩月合併**評估） |
| **Confirm** | 2026-07-01～ | 🔲 未來 UAT 累積 | Paper / shadow |

**2026-06 落地**：UAT `TICK_ARCHIVE=1` 收盤壓縮，或 `python -m backfilldata` 補歷史；完成後更新本表「實際檔數」。

**2025 backfill**：自 **2025-01** 起向前補 tick/kbars；補完跑 `cache_audit`。**禁止**用全段 2025+2026 事後選參再假裝 holdout。

---

## 實際檔數（2026 tick_cache · 2026-06-28）

| 月份 | tick CSV | kbars CSV | 角色 |
|------|----------|-----------|------|
| 2026-01 | 21 | 21 | train |
| 2026-02 | 11 | 11 | train |
| 2026-03 | 22 | 22 | train |
| 2026-04 | 20 | 20 | valid |
| 2026-05 | 20 | 20 | holdout A |
| 2026-06 | — | — | holdout B（待補） |

**合計（就緒）**：94 tick 交易日（01–05）。sweep / CF 前 `cache_audit` **無 FAIL**。

### 2025（待 backfill 後填寫）

| 月份 | tick CSV | kbars CSV | 備註 |
|------|----------|-----------|------|
| 2025-01 … 2025-12 | TBD | TBD | WFO folds only |

---

## 2026 競賽切分（FT-003 · 不變）

| 用途 | 月份 | 可否依結果調 grid |
|------|------|-------------------|
| Train | 01、02、03 | 是 |
| Valid | 04 | 是 |
| Holdout（v1 單月） | 05 | **否** |

全月探索性 `--from-date 2026-01-01 --to-date 2026-06-30` 可跑，**不得**用於選參或 leaderboard。

---

## 建議 CLI 日期參數

```bash
# Train（Q1）
--train-from 2026-01-01 --train-to 2026-03-31

# Valid
--valid-from 2026-04-01 --valid-to 2026-04-30

# Holdout v2（05+06 合併 — 新 thesis）
--holdout-from 2026-05-01 --holdout-to 2026-06-30

# Holdout v1（僅 05 — 已完成之 FT-006/009）
--holdout-from 2026-05-01 --holdout-to 2026-05-31

# WFO fold 例（2025 Q1 測試 — backfill 後）
--train-from 2025-01-01 --train-to 2025-03-31  # 僅作 fold 設計範例
```

`param_sweep` 的 `dates_train` / `dates_valid` 須用 **tick_cache 內實際交易日 list**。

---

## 市場尺度診斷

01～05（及 backfill 後 2025）可用於 **描述統計**（[`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md)）。  
**2026-05 / 06** 統計可作 holdout **風險敘事** — **禁止**依 holdout 分布回頭改已封印 grid。

---

## 更新紀錄

| 日期 | 變更 |
|------|------|
| 2026-06-26 | 初版；2026-01～05 |
| 2026-06-26 | 刪 02-12/13/23；合計 94 日 |
| 2026-06-28 | **HOLDOUT v2**：05+06 合併 holdout；2025 WFO 區段；連結 [`HOLDOUT_CONTRACT_v2.md`](../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) |
