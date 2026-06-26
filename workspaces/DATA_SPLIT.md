# FT-003 資料切分（2026 tick_cache）

> **SSOT**：本檔日期清單須與 `tick_cache/` 內實際檔名一致。  
> 產生精確交易日列表：`cd apps/trading-app/src && python -m backtest --dates-from-cache --cache-dir ../../tick_cache --from-date YYYY-MM-DD --to-date YYYY-MM-DD`（dry-run 看 log 的 count/range）。

## 實際檔數（2026-06-26 更新）

| 月份 | tick CSV | kbars CSV | 備註 |
|------|----------|-----------|------|
| 2026-01 | 21 | 21 | 首日 **01-02**（元旦休市）；tick/kbars 已對齊 |
| 2026-02 | 14 | 14 | |
| 2026-03 | 22 | 22 | |
| 2026-04 | 20 | 20 | valid 競賽區間 |
| 2026-05 | 20 | 20 | holdout（封印） |

**合計**：97 tick 交易日（2026-01-02～2026-05-29）。sweep 前仍須 `cache_audit` PASS。

## 有 1～5 月資料 ≠ 一次回測 1～5 月

`tick_cache` **涵蓋 2026-01～05**，但 FT-003 **禁止**把五個月合併當 in-sample 調參（overfitting）。正確用法：

| 用途 | 月份 | 可否依結果調 grid |
|------|------|-------------------|
| Train（sweep in-sample） | 01、02、03 | 是（診斷） |
| Valid（競賽排名） | 04 | 是 |
| Holdout（最終檢定） | 05 | **否**（Phase 4 解封跑一次） |

全月探索性回測（例如看全年走勢）可跑 `--from-date 2026-01-01 --to-date 2026-05-31`，但**不得**用該結果選參或寫入 leaderboard。

## 切分原則

| 區間 | 月份 | 用途 | AI / sweep 可否看結果做決策 |
|------|------|------|------------------------------|
| **Train** | 2026-01、02、03 | In-sample、診斷 | 是 |
| **Valid** | 2026-04 | 競賽排名、迭代 | 是 |
| **Holdout** | 2026-05 | 最終檢定 | **否**（僅選舉前解封一次） |

## 建議 CLI 日期參數

```bash
# Train（Q1）
--from-date 2026-01-01 --to-date 2026-03-31

# Valid（競賽評分）
--from-date 2026-04-01 --to-date 2026-04-30

# Holdout（封印至 Phase 4）
--from-date 2026-05-01 --to-date 2026-05-31
```

`param_sweep` 的 `dates_train` / `dates_valid` 應使用 **tick_cache 內實際存在的交易日 list**，不要用含週末的曆日 generator。

## 更新紀錄

| 日期 | 變更 |
|------|------|
| 2026-06-26 | 初版；假設 2026-01～05 連續補齊 |
| 2026-06-26 | 1 月補齊（21 tick / 21 kbars）；合計 97 日；新增「有資料 ≠ 合併調參」說明 |
