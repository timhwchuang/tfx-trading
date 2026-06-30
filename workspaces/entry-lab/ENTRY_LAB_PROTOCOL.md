# Entry Lab — 研究協議（v1.2 · pre-registered）

> 跑數據前封印。變更須 bump 本檔 version 並註明日期。  
> v1.2（2026-06-30）：R4 完整定義移至 [`ENTRY_LAB_VOLATILITY.md`](ENTRY_LAB_VOLATILITY.md)。

## 切分

| Split | 日曆 | 用途 |
|-------|------|------|
| **train** | 2025-01-01～2025-12-31 | 探索 |
| **valid** | 2026-01-01～2026-03-31 | confirmatory（見樣本分級） |

## RQ 操作化

| RQ | 指標 |
|----|------|
| RQ1 | `pct_w300_pos`, `pct_w900_pos`, `pct_w1800_pos` |
| RQ2 | W5→W15→W30 median；`giveback_w5_to_w30` |
| RQ3 | `exit_gap`；`pct_net_pos`；exit reason 分佈 |
| RQ4 | regime R1–R4；進場解剖 bucket |

**Path** = stop-less `post_entry_forward` · **Contract** = sim gross/net

## 樣本分級

| n | 結論層級 |
|---|----------|
| ≥30 | 描述 + bootstrap 95% CI |
| 15–29 | 僅描述；CI 標「寬 · 探索性」 |
| <15 | `power_insufficient` · 假說生成 only |
| <10 | 禁止進主文子群表 |

**Slug tier**：FRP/SFBT=Primary · GDC=Secondary · GUDT=Tertiary（valid 子群 confirmatory 不適用）

## Regime（@ entry_ts · 無 lookahead）

| ID | 定義 | Long 順勢 |
|----|------|-----------|
| R1 | `compute_trend` | `trend_dir==Long` |
| R2 | `structure.bias` | `bias==Long` |
| R3 | session 位置 | `in_discount` |
| R4 | 波動 | `atr_percentile_session≤50`（定義 · H1/H2 · 欄位 → [`ENTRY_LAB_VOLATILITY.md`](ENTRY_LAB_VOLATILITY.md)） |

**GDC 特例** `gap_up_structure_bear`：`gap_pts>MIN_GAP` ∧ `bias==Short` ∧ `direction==Long`

## Bootstrap

- 10,000 resamples · **seed=42**
- 不報 p-value；報 95% CI

## MDE 註記

檢出 Δp=15pp @ α=0.05 power=80% 所需 n；不足則 `underpowered_for_15pp`

## Promotion（Lab→Playbook）

1. 可程式化 + 本質差異
2. Path：子群 `pct_w900_pos` +≥10pp，CI 下限 >+3pp
3. Contract（若宣稱）：`net_median` +≥3pt，CI 下限 >0
4. Train 與 valid 同向（valid 子群 n≥15）
5. 人類 §Decision

## Corpus 校驗（Phase 1.5）

Export `n` **必須** == baseline `entry_count_by_param[p0_key]`；否則 STOP。
