# tick_cache 稽核紀錄（SSOT）

> **用途**：記錄最近一次全庫 `cache_audit` PASS，避免每次 Phase 0 CF 重跑整庫掃描。  
> **指令**：`cd apps/trading-app/src && python -m storage.cache_audit --code TMFR1`

---

## 最近一次全庫 PASS

| 欄位 | 值 |
|------|-----|
| **日期** | 2026-06-28 |
| **範圍** | TMFR1 全 `tick_cache/`（2025 train + 2026 Q1 valid 涵蓋） |
| **結果** | 無 FAIL（僅零成交量 tick WARN） |
| **關聯** | FT-012 Phase 0c · Phase 3.6 診斷 |

---

## 何時 MUST 重跑

| 情境 | 指令 |
|------|------|
| **backfill 新日期** | `cache_audit --code TMFR1 --from-date YYYY-MM-DD --to-date YYYY-MM-DD`（只掃新增日） |
| **`cache_repair --fix` 後** | 同上，或全庫若改動面大 |
| **懷疑 tick/kbar 不一致** | 單日 `--date YYYY-MM-DD -v` |
| **首次建立環境** | 全庫 `--code TMFR1` |

## 何時 **不必** 重跑

- 同一批 `tick_cache` 上 **重跑 CF / 改參 / 改 gate_report**
- Code review 後重跑 train（資料未變）
- 僅改 reporting 程式或文件

**規則**：CF CLI **不**內建 `cache_audit`；Agent 預設 **跳過**，除非上表 MUST 情境或本檔 stamp 過期（>30 天且期間有 backfill）。

---

## 更新本檔

全庫或增量 audit PASS 後，更新上方表格（日期、範圍、結果一行）。
