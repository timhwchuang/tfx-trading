# Phase 4 第一輪錯誤經驗（Setup A，2026-09-04）

> 本輪證偽的是「現行 Setup A 猜測／這張 grid」，不是「程式交易沒救」。
> 改規則須先改 `ROADMAP_SMC_BACKTEST.md`，再改 code。

## 1. 結果一句話

**`verdict = no_go`**：無 plateau／elect。有成交的格子全部 `expected_nt < 0`，且一年 IS 最多 **8** 筆（≪ `MIN_IS_TRADES=30`）。

## 2. 硬數字（可複核 `sweep/grid.csv`）

| 觀察 | 數字 |
|---|---|
| conservative 216 格 | 108 零成交／108 有成交 |
| `require_external=True` | **108/108 零成交** |
| `require_external=False` | 108/108 有成交，EV 全負 |
| IS 最多成交 | **8** |
| EV > 0 | **0** |
| cons vs opt | **216/216 逐格相同** |
| walk-forward | 10 折皆 `insufficient_sample` |

Plateau 要同時：`n_trades >= 30` **且** `expected_nt > 0` **且** 鄰居也獲利 → 本輪兩邊都失敗。

## 3. 真槍 blotter 學到什麼

高頻代表格（`ext=False, min=15, buf=3, tp=2R`，8 筆）：

- **entry_stopped ×4**（同一根 1m 進場即掃）
- **stop ×3**（約 −1.2R～−1.3R）
- **target ×1**
- 來回費用約 **49 NT** → 小毛利變渣；同根掃常變 ≈−3R

漏斗（IS）：arm 後約 **92% 死在 `no_sweep`**；`require_external=True` → intents=0。

微台 **1m 可動很大（數百點量級）**；固定 3／5／8 點 buffer 的尺度不足。

## 4. 我們猜錯了什麼

1. 進出場定義偏空泛（「有 sweep／有 FVG」不夠）→ 漏斗空、槍稀。
2. 風險距離用固定點數掃 → 跟不上 1m 波動與費用地板。
3. `require_external` 當掃描維度 → 本段 tape 上是全滅開關，不是品質旋鈕。
4. 以為 fill_mode 會分出 optimistic edge → 這批單 cons≡opt，不是故事主軸。

## 5. 下一假設（尚未改 code）

1. **收斂進場**：把有效 sweep／FVG 互動寫具體，先打 `no_sweep`（優先於加 RSI／VWAP）。
2. **波動感知風險**：停損／最小風險對費用地板與近期波動（如 ATR）掛鉤。
3. **`entry_stopped` 明規則**：風險≤費用地板則不進，或停損晚一棒掛。
4. **`require_external`**：本輪當已知死路；下一張主掃描不指望它。
5. RSI／VWAP／profile／footprint：排在進場收斂之後，各自獨立 Setup。

## 6. Reviewer 請幫忙看

- 上述解讀是否過擬合「事後故事」？
- `MIN_IS_TRADES=30` 對日盤 5m setup 是否合理，或應先承認射頻假設錯了？
- 下一刀應先砍進場定義，還是先砍停損幾何？
