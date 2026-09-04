# 日盤 ORB — 給下一位（測量，不是 elect）

> 聊天紀錄不保證可見。把本文整段貼給下一個 AI plan/chat 當需求。
> 契約仍是 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md)。
> A′ 日盤 elect 不通：[phase4_round2_2026-09-04/CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md)。
> 寫任何 `decide()` 之前先讀 [TMF_DESK_CARD.md](../TMF_DESK_CARD.md)。
> **不要勾 Phase 4。不上 live。不要開第二份 roadmap。**

## 一句話

**08:46–09:00 那根 15m 當框；09:15 前不交易；之後第一根 5m 收盤穿框；停損在 15m 另一側；2R 或 13:40。**  
June 紙上不是 edge。下一步是 1–3 個月 **conservative 引擎**，不是再開 June 旋鈕。

這不是 Setup A / A′ 的延續，也不是立刻做 Setup B。A′ 已收工。Setup B（`taken` 延續）停在旁邊，獨立 setup，尚未開 plan。

## 若你是下一個 agent

1. 讀完本文再動手。規則已鎖定；不要先「再量一個框」。
2. 本目錄目前只有這份交接文。還沒有 `setup_orb.py`、還沒有 conservative 產物。
3. 允許寫 `setup_orb.py` 當**測量載具**。那不是 elect、不是 Phase 4 go、不是 grid。
4. 組框用當日 **08:50 + 08:55 + 09:00 三根 5m** 的 high/low。不要先濾 `session_kind == "day"` 再 resample。不要改 `session_kind`。不要改 `DecisionContext`。
5. 第一段引擎窗：`fill_mode=conservative`，**2025-06-02 → 2025-08-29**。產物寫回本資料夾。
6. 門檻沿用主 roadmap：`MIN_IS_TRADES=30`、不停損晚一棒、不把 `min_r=15` 當雜訊地板、不開 grid、不勾 Phase 4。

## 鎖定規則（紙上已選，不要再扭）

多方；空方鏡像。

| 項 | 規則 |
|---|---|
| 框 | 時鐘 **08:46–09:00**（close label **09:00**），不是 09:15 那根 15m |
| 禁做 | `no_trade_before=09:15`。第一根可發訊號的 5m 是 **09:20** |
| 觸發 | 09:15 之後第一根 5m **收盤** 在框外（不是 wick） |
| 進場 | 限價在框的 high（多）/ low（空） |
| 停損 | 框對側。R = 全框寬 |
| 費用殺閘 | 寬度 `< 15` 不 arm（約 3× 來回）。**不是**雜訊地板 |
| 停利 | 固定 2R |
| 強平 | 13:40 flatten |
| 頻率 | 一天一筆；成交後當日不再發 |
| 日曆 | 結算日整天跳過；日盤 only |

引擎只在合法 5m close 叫 `decide()`。09:00 close 時框已在，但仍在禁做窗。09:15 close 仍 `<= 09:15`。09:20 才允許 arm。

`DecisionContext` 只有 `bar_1m` + `bars_5m` prefix。引擎 `BarStore` 吃全日 1m，`resample_5m` 的 08:50 已含 08:46–08:49。三根 5m 的 H/L = 09:00 15m 框。不要為了 ORB 去擴 `DecisionContext`。

## June 2025 紙上（不是 edge）

20 個日盤，跳過 6/18 結算。未扣成本、不是引擎、`fill_mode` 未跑、不是 elect。

| | |
|---|---|
| 出手 | **20/20** |
| 出場 | 6 stop / 9 flatten / 5 次 2R |
| 平均 R | **+0.22** |
| 框寬 | P50 **67.5**（min 39 / max 146）；沒有一天 `< 15` |
| 09:20 | **11/20** 第一槍（kill zone 溢出，是故事的一部分，不是 bug） |

普通日核對：**2025-06-13**（當日高低 245 ≈ 尺度卡日振幅 P50 243）。09:00 框 22049 / 21903（146 點，含 08:46 wick）。09:20 5m 低 21893 但收 21911 在框內 → 不空。09:50 5m 收 22082 穿上沿做多；flatten 13:40 **−0.63R**。當日高 22138 到不了 2R 22341。

**不要因為 +0.22 就 elect。** n=20、沒成本、沒 OOS。

## 已量過、不要重做

這些是 June 紙上對照，不是新故事：

| 變體 | June 結果 | 為什麼停 |
|---|---|---|
| 1m OR 08:46–09:15 + 5m 收盤 | 20/20；8 stop / 11 flatten / 1 次 2R；平均 −0.15R | 框太大，flatten 為主 |
| 15m **收盤** 確認（第一根合格 15m = 09:30） | 19/20；平均 −0.08R | 沒改故事 |
| 誤把 09:15 15m 當框 | 幾乎等於 1m OR | 濾掉 08:46–08:49 的腳槍，見下節 |
| 5m 訊號棒停損（進場仍用框沿） | 有效 n=13；風險 P50 18；**6 天 R&lt;15、4 天 &lt;10** | 費用殺閘換皮，不是更緊的 ORB |
| 跳過 09:20（15m 對側停） | n=9；平均仍約 +0.21R | 沒改故事 |
| 09:05 就允許交易 | **沒有**當獨立故事數過 | 那是打 open，另開計數；現在禁止 |

## 分析腳槍：`session_kind` ≠ 開盤時鐘

CSV / [BAR_MULTI_TF_DECISIONS.md](../BAR_MULTI_TF_DECISIONS.md)：沒有已收 08:45；第一根 1m 通常是 **08:46**。June 20/20 檔都從 08:46 起。

`session_kind` 日盤是 **08:50–13:45**。08:46–08:49 → `None`。引擎 `decide()` 只在 5m close；第一根 5m 是 08:46–08:50 → **08:50**。那四根 1m **會**進 08:50 5m，只要它們在 `BarStore` 裡。

**先濾 `session_kind == "day"` 再 `resample_15m`：** 丢掉 08:46–08:49 → 08:46–09:00 那桶不滿 15 根 1m → 被丟 → 第一根 15m 變成 **09:15**。June 有 13/20 天，1m OR 高低會因丢掉這四根而變。

ORB / kill zone：**用時鐘 08:46–13:45**，不要用 `session_kind == "day"` 當 1m 濾網。  
**不要改 `session_kind`**，除非人類先改 [BAR_MULTI_TF_DECISIONS.md](../BAR_MULTI_TF_DECISIONS.md) 再開契約變更。

Desk card 開盤雜訊窗寫 08:50–09:14，對齊 `session_kind`；08:45–09:15 中位同樣約 19。那是尺子，不是「第一根 15m = 09:15」。

本地 canvas 不進 git，不要當 SSOT。

## 本 commit 不做；下一位要做

1. `tim_chuang/tfx_trading/strategy/setup_orb.py`：純 `decide()` → `list[Intent]`。測量載具，**不是 elect**。
2. `tim_chuang/tests/test_setup_orb.py`：手工序列鎖幾何（09:00 框、09:15 不發、一天一筆、寬度 &lt; 15 不 arm、結算日不發、空方鏡像）。
3. 第一段 conservative：接現有 `backtest.engine` + Broker，`fill_mode=conservative`，日期 **2025-06-02 → 2025-08-29**（含 June 紙上月）。
4. 產物寫回本資料夾：`SMOKE.md` / json / trade log（git hash + 參數 + 資料範圍）。**不是 go/no-go。**
5. 之後若槍數與扣成本後的平均 R 看起來不像死路，再把窗拉到更長（仍 conservative，仍不開 grid）。不夠就關，標準與 A′ 相同：樣本、費用、flatten，不是再扭框。

限價走引擎既有 conservative trade-through。停損優先、同根進場即停，維持全域不變量。不要為了少 `entry_stopped` 把停損晚一棒掛。

## 怎麼跑（這個 repo）

- 只動 `tim_chuang/`。當 `apps/`、`legacy/`、`tick_cache/`、根 `docs/AGENTS.md` 不存在。
- 工作目錄：`tim_chuang/`。直譯器：`.venv/bin/python`。Python ≥ 3.14。
- kbars：`tim_chuang/tfx_trading/kbars_data/`（不是 `tim_chuang/kbars_data/`）。
- 長 tape 用 CLI，不要塞進預設 pytest。
- 改規則先改 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md) 再改 code。

## 明確禁止

- 重開 A′ Step 3b、改 `setup_a.py` 養樣本、第二輪 `python -m tfx_trading.backtest.sweep`
- 為製造 `go` 降低 `MIN_IS_TRADES`；停損晚一棒；把 `min_r=15` 當雜訊地板
- 勾 Phase 4；上 live；開第二份 roadmap
- 放寬到 09:05；改用 5m 訊號棒停損；跳過 09:20 當「下一刀」
- ORB × SMC / RSI / VWAP 交叉 grid
- 夜盤 ORB（不是把日盤框接到 15:05）
- 與 Setup B 並行開 plan
- 把 June +0.22R 或本地 canvas 當 elect 證據

## Setup B（停放）

獨立 **Setup B：`taken` 延續**。先日盤普查，先改 roadmap，再另開 plan。不是 A′ 延到 15:05，也不是現在這條 ORB 的下一步。
