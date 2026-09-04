# 這條路不通：Setup A / A′ 日盤 elect

> 給之後讀到 `setup_a.py`、`sweep.py`、或「再收斂進場」的人。
> 契約：[ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md)。
> **不要勾 Phase 4。不上 live。不要為了救樣本去改 `decide()`。**

## 一句話

**日盤 sweep → event → 回踩 FVG，在這年 IS 選不出 plateau。**  
不是還沒改 CHoCH，不是成交率沒量完，不是再掃 432 格就會通。

命名的確認（FVG 落在 sweep **當根或同一 session 下一根 5m**）在這張 tape 上是 **0 筆**。latest-wins 選到的 17 筆全是更晚的 FVG。17 就算全成交也 `< MIN_IS_TRADES=30`。

## 若你是下一個 agent

1. 讀完本文就停 **A′**。不要開 Step 3b plan，不要改 `preferred_event` / FVG 窗去養 n。下一刀見第 4 點。
2. 不要跑第二輪 `python -m tfx_trading.backtest.sweep`。第一輪 `no_go` 產物在 `docs/phase4_round1_2026-09-04/`，那是複核檔，不是許可再掃。
3. `setup_a.py` 的 sweep 極值停損與 `min_r_points=15` 留著；那是幾何與費用，不是 elect。
4. 下一刀是日盤 **ORB**（測量，不是 elect）：[orb_day_2026-09-04/README.md](../orb_day_2026-09-04/README.md)。不是 A′ 接到夜盤 15:05。Setup B（`taken` 延續）仍停放。

## 證據

| 證據 | 數字 | 出處 |
|---|---|---|
| nested unique（bias+sweep+event+FVG≥15） | **17**（5 / 12） | [census/FINDINGS.md](census/FINDINGS.md)、尺度卡 |
| nested CHoCH+FVG≥15 | **16**（5 / 11） | [funnel/FUNNEL.md](funnel/FUNNEL.md) |
| chosen FVG same / next / later | **0 / 0 / 17**；shadowed **0** | 同上 |
| conservative spells → fills | 42 → **8**（thesis cancel 32、expire 2） | 同上 |
| `MIN_IS_TRADES` | **30** | roadmap |

硬切 same/next 會先把 17 變成 0。只 require CHoCH 幾乎不動射頻。8/42 不是 edge。

## 明確禁止

- 不實作 CHoCH 硬閘 / impulse 窗寫進 `decide()`（原 Step 3b）
- 不開第二輪 `GridSpec`
- 不降低 `MIN_IS_TRADES`、不停損晚一棒、不把 later FVG 繼續當「確認」
- 不把 RSI／VWAP 塞進 A′、不加年份把 17 灌到 30
- 不把 42 spells 湊近 17 unique
