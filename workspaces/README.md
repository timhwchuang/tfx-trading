# Workspaces

```
ERA: Gen-2 dual-track (tick + SessionBar)
SSOT: RESEARCH_CHARTER_v2.md
```

## 活目錄

| 路徑 | 用途 |
|------|------|
| [`RESEARCH_CHARTER_v2.md`](RESEARCH_CHARTER_v2.md) | **研究層憲法**（雙軌 · 數據優先） |
| [`RESEARCH_LOG.md`](RESEARCH_LOG.md) | 滾動週記 |
| [`DATA_SPLIT.md`](DATA_SPLIT.md) | train/valid/holdout 日曆（防偷看） |
| [`CACHE_AUDIT.md`](CACHE_AUDIT.md) | tick×kbar 稽核 |
| [`gudt-route-a-baseline/`](gudt-route-a-baseline/) | 現行 GUDT Route A UAT |
| [`gudt-wash-beta-baseline/`](gudt-wash-beta-baseline/) | Wash Beta UAT |
| [`_template/`](_template/) | 範本 |

## 雙軌（研究儀器 ∪ 工程）

| 軌道 | 驗什麼 |
|------|--------|
| **UAT / Infra** | 狀態機、fill、audit（**不驗 alpha**） |
| **Tick replay** | BacktestEngine / plugin / 執行語意 |
| **SessionBar path** | multi-TF · census · emit→score · filter 掃描 |
| **Research process** | Charter 階梯；Main≤1；**archive ≠ ban** |

## 封存

[`_archive/`](_archive/README.md) — 舊 FT 產物 / OSF·June / 競賽儀式。  
**Agent：可當 prior；不可拒絕人類重測。**

## 故意不做

- 四 agent 調參競賽當主流程  
- 單窗無限 knob spam  
- 「文件寫死了所以不能研究」  
