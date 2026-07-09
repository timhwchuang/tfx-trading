# GUDT Wash Champion 探索 — 2026-01～05

> Exploratory · 非封印 · holdout 前候選

## H1 合計（37 個 GUDT 相關日）

| 策略 | n | net_total |
|------|---|-----------|
| 封印 p0 + sealed | 24 | **+150** |
| p0 + drive_low_struct | 24 | +113 |
| flow_turn + drive_low（全日） | 35 | +1446 |
| **early_ft else p0+dl** | **37** | **+1408** |

### Champion 候選規則（可實作）

```
進場：
  若當日有 flow_turn 且 entry_ts < p0（或無 p0）→ flow_turn
  否則 → p0

出場：drive_low_struct
  BE off · stop = drive_low − 2 · hold 900s
```

Wash 參數：`min_wash_k=0.25` · `br_min=0.55` · `delta_br_min=0.12`

### 月分解（early_ft else p0+dl）

| 月 | n | net |
|----|---|-----|
| 01 | 5 | +223 |
| 02 | 6 | +155 |
| 03 | 6 | **-117** |
| 04 | 12 | +709 |
| 05 | 8 | +438 |

3 月仍虧 — champion 非全季萬能。

### vs 單純 depth+dBR 規則

`depth≥0.25ATR & dBR≥0.12 → ft+dl` 會在 **01-05** 誤判（應 P0），合計約 +752。  
**時序規則**（flow_turn 早於 P0）較穩。

## Holdout 建議

| 區間 | 用途 |
|------|------|
| **2026-01～05** | tune / champion 候選（本報告） |
| **2025-05～11** | holdout A（舊半年，下載後跑同一 probe） |
| **2026-06** | holdout B（未來，出爐後一次驗證） |
| 2025-12 | 可選 bridge valid（與封印 train 重疊，勿重 tune） |

**封印條件（建議）**：holdout A+B 合計 net > 0 且單月無災難月（<-150）；否則維持 `gk1_rt0p4_...` 封印。
