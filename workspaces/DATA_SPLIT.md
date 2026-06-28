# 資料切分 SSOT（tick_cache · TMFR1）

> **策略 thesis（FT-011+）**：**[`HOLDOUT_CONTRACT_v2.md` v2.1](../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)** — 2025 train · 2026 Q1 valid · 2026 Q2 holdout。  
> **已結案 FT（006–010）**：[`HOLDOUT v2 §2.0`](../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) legacy 切分，結論不重跑。  
> **FT-003 grid 競賽**：下表「2026 競賽切分」仍有效。

## 涵蓋範圍

| 區段 | 日曆 | 狀態 | 用途 |
|------|------|------|------|
| **Train** | **2025-01-01～2025-12-31** | ✅ **247 日** | v2.1 Phase 0 主判 |
| **Valid** | **2026-01-01～2026-03-31** | ✅ **54 日** | v2.1 參考 / overfit |
| **Holdout** | **2026-04-01～2026-06-30** | 04–05 ✅ · **06 待落地** | v2.1 封印（三月） |
| **Confirm** | **2026-07-01～** | 🔲 | Paper / shadow |
| **Legacy** | 2026 01–03 / 04 / 05 | ✅ | FT-006～010 封存 |

CF / sweep 前：`python -m storage.cache_audit --code TMFR1`（**無 FAIL**）。

---

## 實際檔數（2026-06-28 稽核）

### 2025（train · v2.1）

| 月 | tick | kbars | 月 | tick | kbars |
|----|------|-------|----|------|-------|
| 2025-01 | 17 | 17 | 2025-07 | 23 | 23 |
| 2025-02 | 20 | 20 | 2025-08 | 21 | 21 |
| 2025-03 | 21 | 21 | 2025-09 | 21 | 21 |
| 2025-04 | 20 | 20 | 2025-10 | 20 | 20 |
| 2025-05 | 21 | 21 | 2025-11 | 20 | 20 |
| 2025-06 | 21 | 21 | 2025-12 | 22 | 22 |

**2025 合計**：**247** tick / **247** kbars。

### 2026

| 月 | tick | kbars | v2.1 角色 |
|----|------|-------|-----------|
| 2026-01 | 21 | 21 | valid |
| 2026-02 | 11 | 11 | valid |
| 2026-03 | 22 | 22 | valid |
| 2026-04 | 20 | 20 | holdout |
| 2026-05 | 20 | 20 | holdout |
| 2026-06 | — | — | holdout（待補） |

**2026 合計（就緒）**：**94** tick / **94** kbars（01–05）。  
**v2.1 valid（Q1）**：54 日 · **holdout（04–05）**：40 日（06 補齊後重算 Q2）。

---

## v2.1 CLI（新 thesis 預設）

```bash
# Train — 2025 全年
--train-from 2025-01-01 --train-to 2025-12-31

# Valid — 2026 Q1
--valid-from 2026-01-01 --valid-to 2026-03-31

# Holdout — 2026 Q2（06 落地後跑滿）
--holdout-from 2026-04-01 --holdout-to 2026-06-30

# Holdout partial（06 未齊時僅存檔）
--holdout-from 2026-04-01 --holdout-to 2026-05-31
```

---

## v2.0 / Legacy CLI（已結案 FT）

```bash
# FT-009 Phase 0 主判（歷史）
--aggregate-from 2026-01-01 --aggregate-to 2026-04-30

# Legacy holdout 單月
--holdout-from 2026-05-01 --holdout-to 2026-05-31
```

---

## 2026 競賽切分（FT-003 · 不變）

| 用途 | 月份 | 可否依結果調 grid |
|------|------|-------------------|
| Train | 2026-01、02、03 | 是 |
| Valid | 2026-04 | 是 |
| Holdout | 2026-05 | **否** |

**禁止**用 2025+2026 全段合併 tune 再宣稱 holdout。

---

## 市場尺度診斷

2025–2026 可用於 [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md)。  
Holdout 區間統計可作風險敘事 — **禁止**依 holdout 分布回頭改已封印 grid。

---

## 更新紀錄

| 日期 | 變更 |
|------|------|
| 2026-06-26 | 初版；2026-01～05 |
| 2026-06-28 | HOLDOUT v2；05+06 holdout |
| 2026-06-28 | **v2.1**：2025 全年 **247 日**落地；train/valid/holdout 前移；legacy §2.0 |
