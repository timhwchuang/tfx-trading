# 日盤 ORB — 給下一位（測量，不是 elect）

> 聊天紀錄不保證可見。把本文整段貼給下一個 AI plan/chat 當需求。
> 契約仍是 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md)。
> A′ 日盤 elect 不通：[phase4_round2_2026-09-04/CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md)。
> 寫任何 `decide()` 之前先讀 [TMF_DESK_CARD.md](../TMF_DESK_CARD.md)。
> **不要勾 Phase 4。不上 live。不要開第二份 roadmap。**

## 一句話

**08:46–09:00 那根 15m 當框；09:15 前不交易；之後第一根 5m 收盤穿框；追價停損單進場；停損在 15m 另一側；2R 或 13:40。**  
June 紙上不是 edge。下一步是 1–3 個月 **conservative 引擎**，不是再開 June 旋鈕。

這不是 Setup A / A′ 的延續，也不是立刻做 Setup B。A′ 已收工。Setup B（`taken` 延續）停在旁邊，獨立 setup，尚未開 plan。

## 若你是下一個 agent

1. 讀完本文再動手。規則已鎖定；不要先「再量一個框」。
2. 本目錄目前只有這份交接文。還沒有 `setup_orb.py`、還沒有 conservative 產物。
3. 允許寫 `setup_orb.py` 當**測量載具**。那不是 elect、不是 Phase 4 go、不是 grid。
4. 組框用當日 **08:50 + 08:55 + 09:00 三根 5m** 的 high/low。不要先濾 `session_kind == "day"` 再 resample。不要改 `session_kind`。不要改 `DecisionContext`。
5. 第一段引擎窗：`fill_mode=conservative`，**2025-06-02 → 2025-08-29**。產物寫回本資料夾。
6. 門檻沿用主 roadmap：`MIN_IS_TRADES=30`、不停損晚一棒、不把 `min_r=15` 當雜訊地板、不開 grid、不勾 Phase 4。
7. 進場已鎖定 **追價（停損／穿越單）**，不是回踩限價。不要改回限價掛框沿等回補。

## 鎖定規則（紙上已選，不要再扭）

多方；空方鏡像。

| 項 | 規則 |
|---|---|
| 框 | 時鐘 **08:46–09:00**（close label **09:00**），不是 09:15 那根 15m |
| 禁做 | `no_trade_before=09:15`。第一根可發訊號的 5m 是 **09:20** |
| 觸發 | 09:15 之後第一根 5m **收盤** 在框外（不是 wick） |
| 進場 | **追價**：收盤穿框後，用 **停損單** 掛在被突破那一側（多 = box high；空 = box low）。**不是**回踩限價等回框沿 |
| 停損 | 框對側。R = 全框寬 |
| 費用殺閘 | 寬度 `< 15` 不 arm（約 3× 來回）。**不是**雜訊地板 |
| 停利 | 固定 2R |
| 強平 | 13:40 flatten |
| 頻率 | 一天一筆；成交後當日不再發 |
| 日曆 | 結算日整天跳過；日盤 only |

引擎只在合法 5m close 叫 `decide()`。09:00 close 時框已在，但仍在禁做窗。09:15 close 仍 `<= 09:15`。09:20 才允許 arm。

`DecisionContext` 只有 `bar_1m` + `bars_5m` prefix。引擎 `BarStore` 吃全日 1m，`resample_5m` 的 08:50 已含 08:46–08:49。三根 5m 的 H/L = 09:00 15m 框。不要為了 ORB 去擴 `DecisionContext`。

### 進場鎖定：追價，不是回踩

鎖定理由（2026-09-05）：

1. 故事是「第一根 5m **收盤已在框外**」＝突破確認。確認後再掛 **限價回框沿** 會變成另一個 setup（回踩／retest），和 June 紙上「穿了就計一筆」不是同一題。
2. June 紙上寫過「限價在框沿」，語意含糊：收盤已穿框後，限價掛在框沿在 conservative 引擎裡常變成「等回踩才填」，或同根 trade-through 的怪邊角。**追價停損單**語意乾淨：突破方向、穿過被破那一側才進。
3. 回踩可以以後當 **獨立 setup** 另開計數；本輪禁止混進 ORB。

實作：`Intent` 用引擎既有 **停損／市價停損** 路徑（多：buy stop @ box high；空：sell stop @ box low）。停損優先、同根進場即停，維持全域不變量。不要為了少 `entry_stopped` 把停損晚一棒掛。訊號棒收盤已在框外時，下一根 1m 若已穿過進場價，依 broker 規則成交；不成交則當日那一槍作廢（一天一筆已消耗或未消耗——實作前在測試鎖死：**觸發日只允許一張在途進場單；未成交到 13:40 取消**）。

## 缺棒／異常日（先 skip，不要硬組框）

下列日子 **整天不交易**（與結算日同級）：

| 條件 | 動作 |
|---|---|
| 08:46–09:00 時鐘窗缺 1m，導致 08:50 / 08:55 / 09:00 任一根 5m 組不出 | skip |
| 三根 5m 齊了但 high == low（框寬 0） | skip（費用殺閘也會擋，明示更好） |
| 日盤提早結束／無 13:40 可 flatten 的短市 | skip（不要改 flatten 鐘點當變體） |
| 結算日 | 已規定整天跳過 |

開盤跳空仍用當日三根 5m 的 H/L 組框；**不要**另開「gap filter」旋鈕。若缺棒導致框與 June 紙上不一致，記在 `SMOKE.md`，不要改組框定義去對齊紙上。

## 第一段殺閘（2025-06-02 → 2025-08-29，conservative）

產物是測量，**不是** Phase 4 `gates.md` go。但要有可執行的死線，避免無限扭旋鈕：

| 閘 | 過線（繼續拉長窗） | 死路（關，標準同 A′） |
|---|---|---|
| 成交筆數 n | n ≥ 30（對齊 `MIN_IS_TRADES`） | n < 30 且不是「幾乎每天有訊號但不成交」的引擎 bug |
| 扣成本後平均 R | > 0（含稅費／手續／停損滑價假設） | ≤ 0，或只靠 optimistic 才正 |
| `entry_stopped` 占比 | 記錄；若 > 40% 先查是否同根不變量誤傷，**不要**晚掛停損 | 修不掉且 EV 仍 ≤ 0 → 關 |
| flatten 占比 | 記錄（June 紙上 9/20）；過高不是立刻改框，是證據 | 與 EV≤0 一起出現 → 關 |
| 費用殺閘觸發 | 寬度 `< 15` 天數；June 是 0 | 大量 `< 15` → 檢查資料／組框，不是把 15 當雜訊地板下調 |

不夠就關。關的標準是樣本、費用、flatten，**不是**再扭框、換回踩、放寬 09:05、跳過 09:20。

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

**不要因為 +0.22 就 elect。** n=20、沒成本、沒 OOS。紙上進場語意以本文「追價」為準；引擎結果與紙上筆數不一致時，以引擎 + 測試為準，並在 `SMOKE.md` 寫差異。

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
| 回踩限價掛框沿 | **沒有**當本輪故事 | 獨立 setup；禁止與追價 ORB 混掃 |

## 分析腳槍：`session_kind` ≠ 開盤時鐘

CSV / [BAR_MULTI_TF_DECISIONS.md](../BAR_MULTI_TF_DECISIONS.md)：沒有已收 08:45；第一根 1m 通常是 **08:46**。June 20/20 檔都從 08:46 起。

`session_kind` 日盤是 **08:50–13:45**。08:46–08:49 → `None`。引擎 `decide()` 只在 5m close；第一根 5m 是 08:46–08:50 → **08:50**。那四根 1m **會**進 08:50 5m，只要它們在 `BarStore` 裡。

**先濾 `session_kind == "day"` 再 `resample_15m`：** 丢掉 08:46–08:49 → 08:46–09:00 那桶不滿 15 根 1m → 被丟 → 第一根 15m 變成 **09:15**。June 有 13/20 天，1m OR 高低會因丢掉這四根而變。

ORB / kill zone：**用時鐘 08:46–13:45**，不要用 `session_kind == "day"` 當 1m 濾網。  
**不要改 `session_kind`**，除非人類先改 [BAR_MULTI_TF_DECISIONS.md](../BAR_MULTI_TF_DECISIONS.md) 再開契約變更。

Desk card 開盤雜訊窗寫 08:50–09:14，對齊 `session_kind`；08:45–09:15 中位同樣約 19。那是尺子，不是「第一根 15m = 09:15」。

本地 canvas 不進 git，不要當 SSOT。

## 本 commit 不做；下一位要做

1. `tim_chuang/tfx_trading/strategy/setup_orb.py`：純 `decide()` → `list[Intent]`。測量載具，**不是 elect**。進場 = 追價停損單。
2. `tim_chuang/tests/test_setup_orb.py`：手工序列鎖幾何（09:00 框、09:15 不發、一天一筆、寬度 &lt; 15 不 arm、結算日不發、空方鏡像、缺棒 skip、追價不是限價回踩）。
3. 第一段 conservative：接現有 `backtest.engine` + Broker，`fill_mode=conservative`，日期 **2025-06-02 → 2025-08-29**（含 June 紙上月）。
4. 產物寫回本資料夾：`SMOKE.md` / json / trade log（git hash + 參數 + 資料範圍）。對照上文殺閘表。**不是** Phase 4 go/no-go。
5. 過殺閘再拉長窗（仍 conservative，仍不開 grid）。不夠就關，寫 `CLOSED.md`（標準與 A′ 相同）。

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
- 把進場改成回踩限價、或與追價交叉 grid
- ORB × SMC / RSI / VWAP 交叉 grid
- 夜盤 ORB（不是把日盤框接到 15:05）
- 與 Setup B 並行開 plan
- 把 June +0.22R 或本地 canvas 當 elect 證據
- 把 ORB 三個月測量誤當成 Phase 4 Setup A 的 `gates.md` 驗收

## Phase 4 checkbox 語意（給人類）

主 roadmap 的 Phase 4 勾選是 **Setup A / A′ 那輪** 的 go/no_go 驗收，不是「任何策略測過就算」。A′ 已 `no_go`／CLOSED；**不要**因為開始做 ORB 就把 Phase 4 勾成完成。ORB 若將來要 elect，另開驗收敘事（或人類明確改 roadmap），不是偷勾舊框。

## Setup B（停放）

獨立 **Setup B：`taken` 延續**。先日盤普查，先改 roadmap，再另開 plan。不是 A′ 延到 15:05，也不是現在這條 ORB 的下一步。
