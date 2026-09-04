# Phase 4 第一輪錯誤日記（2026-09-04）

給下一個讀這輪產物的人。不是績效報告。

## no_go 一句話

現行 Setup A 猜測 + 這張 216 格 grid,在 `2025-03-03`→`2026-03-02`、seed `42`、
git `159b651` 下 **`verdict = no_go`**,`elected = null`,五條硬閘全未過(無 plateau)。
證偽的是這套進出場定義,不是「回測框架壞了」或「從此不要做系統」。

## 硬數字(不要再猜)

- `require_external=True`:108/108 組 `n_trades=0`
- `require_external=False`:108/108 有成交,但**全部 `expected_nt < 0`**
- 最多 **8** 筆(≪ `MIN_IS_TRADES=30`)
- conservative 與 optimistic **逐格相同**(fill 差異未分開這批單)
- Walk-forward 10 折皆 `insufficient_sample`(train 無任一格 ≥30 筆)
- 因此 70/30 選舉、OOS EV、衰退、slip2 壓力全部沒有候選可測——閘門不是「差一點」,是沒入場券

細節與 checkbox 見 `sweep/gates.md`(後續 commit 補上;與 harness `_gates_md` 同格式)。
grid 列見 `sweep/grid.csv`;折次狀態見 `sweep/walk_forward.csv`。

## Blotter / 漏斗

代表格(IS 171 日盤;ext=False, min=15, buf=3, 2R):8 筆

- 出場:`entry_stopped`×4 / stop×3 / target×1
- 費用來回約 **49 NT**,放大小虧
- 同根 1m 進場即掃常見(全域不變量 3 的「進場後立刻停損」不是理論,是這批單的主路徑)

漏斗:

- arm 後約 **92%** 死在 `no_sweep`
- `require_external=True` → intents=0

原始流水放 `blotter/`(後續 commit)。先讀數字再打開 CSV。

## 我們猜錯了什麼

1. **以為「SMC 組合拳寫進 `decide`」就夠形成可掃的 setup。**
   進出場定義偏空泛:大量 armed,幾乎都死在 `no_sweep`;
   過線的單又少到統計上不能比參數。
2. **以為固定 3/5/8 點 buffer 是合理的第一張 grid。**
   1m 可動很大(數百點量級);固定點尺度不夠,費用地板(~49 NT 來回)就能吃掉小虧。
3. **以為 `require_external=True` 會濾出「比較真」的確認。**
   本輪它是已知死路:108/108 零成交,intents=0。不是「比較嚴、樣本少但仍有 edge」。
4. **以為 conservative vs optimistic 會拆開這批限價單。**
   逐格相同——這批單的成敗不在 touch / trade-through 邊界。
5. **以為走完 216×2 fill 就能選 plateau、再 walk-forward。**
   沒有任一格達到 `MIN_IS_TRADES`;WF 10 折全部 `insufficient_sample`。
   掃描證明的是「定義太鬆 + 尺度不對」,不是「參數還沒掃到甜蜜點」。

## 下一假設（尚未改 code）

改規則先改 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md),下列**尚未實作**:

1. **進場定義收斂**:把「有效 sweep／FVG 互動」寫具體,先打 `no_sweep` 漏斗
   (優先於加 RSI／VWAP)
2. **波動感知風險**:停損／最小風險距離對費用地板與近期波動(例如 ATR)掛鉤;
   檢討固定點 buffer grid
3. **`entry_stopped` 政策**:風險≤費用地板則不進,或停損晚一棒掛——寫成明規則
4. **`require_external`**:本輪視為已知死路;下一張 grid 不指望它救命
   (可留參數但預設 false／移出主掃描)
5. RSI／VWAP／profile／footprint:仍排在 A′ 進場收斂之後,各自獨立 Setup,
   不塞進同一張超大 grid

## 想請 reviewer 看的問題

1. 同不同意「證偽的是現行 Setup A 猜測／這張 grid,不是系統交易本身」?
   若不同意,卡在哪一條證據(漏斗、`n=8`、費用、還是閘門定義)?
2. 下一刀優先打 `no_sweep` 進場定義,而不是先加 RSI／VWAP／市場狀態濾網——這個排序是否同意?
3. `require_external` 下一張主掃描:預設 false 留參數,還是直接移出 grid?
4. `entry_stopped`:「風險≤費用地板不進」vs「停損晚一棒掛」,有沒有你比較想先寫成明規則的那個?
   還是兩個都要、當獨立假設分開測?
5. 波動尺度用 ATR(哪一週期、多少倍)是否夠當 v1,或你認為該對 session range / 當日已走點數掛鉤?
6. Phase 4 checkbox 維持打開,直到未來某一輪真的 `go`——這點請確認不要被這份產物誤勾。
