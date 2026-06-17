1. 程式碼品質與架構（高分）
• Protocol 遵守極佳：完全尊重 trading-engine 的 Strategy Protocol + RiskGate 所有 gate（pending、cooldown、block_new_entry、after_flatten_time、force_flatten、daily loss block side effect、consecutive_loss 等）。從不自己發明狀態機或繞過 kernel。這點很多策略 plugin 都做不到。
• 狀態隔離正確：MomentumState 嚴格留在 plugin 內部（reset() 乾淨）。沒有把策略狀態污染到 Protocol 或 engine。
• 可測試性與可觀測性一流：SignalAudit 涵蓋 pullback、stop_loss、stop_loss_vwap、take_profit、trailing_stop、session_force_flatten、trend_veto（帶完整 context）。這不是裝飾，是為 UAT 校準而生的 instrumentation。尤其是 trend_veto 故意讓你能看到「被濾掉的候選」，這對之後算 filter 的 delta expectancy 至關重要。
• 測試策略正確：有純 Protocol 測試（直接 mock MarketSnapshot/PositionSnapshot/RiskGate）、數學性質測試（trend）、行為邊界測試（grace period 用 exchange ts、cooldown 尊重 gate、session flatten、gap hygiene regression）。test_trend.py 裡那個 P6-1-CAL-1 的 quantitative guard（證明未切片輸入會從 stale data 製造假 regime）特別有水準。
• Lint/format 全過（ruff），mypy 只剩一個小註記（_try_activate_momentum 回傳型別），CI 已處理為 non-blocking。py.typed + entry point + 乾淨的 packaging。

唯一小扣分：MomentumState.peak 被寫入（activate + update_momentum_peak），但從未被讀取用於決策或 audit。屬於歷史遺留的死程式碼。v0.1.0 前建議移除或接上 obs。

2. 進場邏輯思考（有架構，不是 naive）
兩階段設計清楚：

1. Momentum 啟動（_try_activate_momentum）：1s 量能門檻 + 買/賣比率不對稱（momentum_buy_ratio / sell_ratio）+ ATR 足夠 + 無持倉 + 所有 risk gate 通過。
2. Pullback 進場（_try_pullback_entry）：必須同時滿足「貼近 VWAP（entry_band_points）」與「量能枯竭（exhaustion_vol）」。

再加上 momentum 180s timeout（合理但建議之後參數化）。

這不是「看到量就衝」或「看到偏離 VWAP 就進」，而是先有微觀動能確認趨勢啟動，再等回檔 + 量縮確認。結構正確。

專業警訊（必須 UAT 驗證）：
• 1s vol + 1s 買賣分類極度依賴資料品質。實務上很容易吃到 quote stuffing、分類延遲、或不同券商/模擬器的 volume 標記差異。這是這套策略最敏感的 micro-structure 賭注。
• 180s timeout 目前硬編碼。

3. 出場邏輯與風險控管（有工程思維）
• Grace period 設計很漂亮：進場後一段時間（ticks 或 sec）只認 hard stop，忽略 VWAP stop。這是針對「進場後 VWAP 微幅震盪就把你震掉」的現實問題做的防護。測試也蓋得很完整（ticks vs time 邊界、Long/Short 都測）。
• 出場優先序與多重條件（hard stop > vwap stop（ATR 動態） > fixed TP > trailing（ATR 動態））清楚，reason 正確。
• ATR 動態（floor + k）可獨立開關 trail / vwap stop，設計彈性好。
• Session force flatten 走 kernel hook + 可配置 slippage + 正確 audit。

小問題：hard stop 以 entry_price 為基準，VWAP stop 以當前 vwap 為基準，這是刻意不同（一個是「我進錯了」，一個是「均值回歸」）。文件沒特別強調這點差異，UAT 時建議寫進決策日誌或 SPEC 補充。

4. Filter 設計（P6-1 Trend Filter 最有看頭）
這部分最能看出不是散戶碼。

• compute_trend 的 Level-2 gating（只有 strength >= min_strength 才發 Long/Short，否則強制 Flat）+ ATR normalization 是正確的工程作法。
• 文件明確警告：「min_strength=0.0 是最嚴格（veto 最多）的設定」，而不是最寬鬆。這點很多做 filter 的人都搞反。
• resample_closes 刻意從尾端對齊保證最新 bar 參與 + SMA-seed warmup 減少第一 bar bias + 明顯的 gap pollution 防護 + 回歸測試證明「舊 heuristic 會吃到前日資料製造假 regime」。
• trend_allows_entry 本身很簡單（Flat 就放行；只有 committed counter-trend 才 veto），威力全來自上游的 Level-2。這是正確的職責切割。

這套 filter 的設計目的是讓你能誠實量測它有沒有幫到忙（靠 trend_veto audit + 之後的 harness）。這是研究型策略該有的態度。

仍需 UAT 重點驗證：
• 不同商品、不同波動 regime 下 min_strength 的實際 veto rate 與 delta expectancy。
• 真實 TrendRefreshPort 提供的 trend_dir/strength 品質（如果它還是用粗糙 resample，filter 的 statistical power 會打折。SPEC 已經誠實寫了「建議改用真 HTF kbar」）。

5. 其他系統交易員會在意的點
• 優點：所有參數走 RuntimeConfig overlay + patch_strategy_params / sweep helpers，研究校準體驗優秀。完全不硬塞預設值（這點比很多策略 repo 強）。
• 限制（非缺點，是 scope）：永遠 qty=1、單一口、不能 scale-in（這是 trading-engine position model 的限制，plugin 正確地沒越權）。
• 依賴 market.current_atr 與 trend_* 的品質，UAT 時要鎖定 engine 版本與 ATR/trend 計算方式。
• 文件（SPEC.md + README + release notes）水準遠高於一般個人策略 repo。

總結判斷（給 v0.1.0 tag 前的建議）

可以打 v0.1.0 並推。

這已經是「第一個公開的 trading-engine strategy reference plugin」該有的水準：
• 架構正確
• 思考有深度（不是單純把舊 theman 程式碼搬過來）
• 測試 + audit + 文件夠支撐後續多人/社群校準
• 姿勢正確（research only + 強烈 UAT checklist 提醒）

進入 UAT 前的硬性建議（非可選）：
1. 把 MomentumState.peak 那段死碼清理掉，或明確接上 obs。 **已處理**：peak 及相關 update_momentum_peak / 呼叫點已完全移除（死碼，無決策或 audit 使用）。
2. 把 180s timeout 至少移到 params 並文件化（或強制記錄在 audit）。 **已處理**：移至 `StrategyParams.momentum_timeout_sec`（支援 RuntimeConfig overlay），文件化於 SPEC.md / README / 程式碼 log，並在 timeout 發生時明確 log 實際 timeout 值。
3. 在你自己的 UAT harness 裡一定要做「with/without trend filter」的 counterfactual 分析（這套設計本來就為了這個）。
4. 拿真實 tick 資料（不是只有 1m close）跑完整交易日，特別盯 1s vol/imb 訊號的穩定度。
5. 嚴格執行 trading-engine 的 UAT_CHECKLIST.md + LIVE_SAFETY.md。

如果你之後要把這套當作 strategy-starter 模板推給其他人，這份品質已經可以當範例（除了上面那兩個小點）。

這不是「我會寫 Python 所以我來寫交易策略」的產物。這是「我懂什麼是 systematic trading research pipeline，所以我把決策、狀態、觀測、校準鉤子、風險 gate 尊重都寫對了」的產物。

可以推 v0.1.0。接下來就是資料與校準的戰場了。