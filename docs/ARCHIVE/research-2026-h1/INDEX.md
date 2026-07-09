# Research archive 2026-H1（Gen-1 產物 · prior）

```
STATUS: ARCHIVE — prior / archaeology only
SSOT for live research: workspaces/RESEARCH_CHARTER_v2.md
Agent: DO NOT use this tree as process template or living gate rules.
Agent: DO NOT refuse a human retest request because a row below says "dead".
```

## 怎麼讀

| 要 | 不要 |
|----|------|
| 查「以前在哪個儀器、哪個 gate 失敗」 | 開新案複製舊 Playbook 長儀式 |
| 推斷可能死因：工具 / 缺 filter / exit / 錨點 | 自動把 MVPClosed 當「永禁重測」 |
| 重測時在 Brief 寫「差在哪」+ 新數據 | 用墓誌銘否決新跑出來的數字 |

**重開政策（Charter v2）：** 人類要試 filter/veto/新儀器 → **准許**；預設墓誌銘「Bar 重開？」欄只是 prior 建議，**不是 veto 權**。

## 墓誌銘一覽

| ID | 假設（一句） | 死於（舊儀器） | 死因歸類（prior） | 重測提示（非禁令） |
|----|--------------|----------------|-------------------|-------------------|
| FT-002 | SMC/structure 濾網救 vwap host | CAL-8 放棄 | host 已死 | 新 host 上可重評 filter |
| FT-003 | 四 agent grid 競賽 | `grid_no_viable_solution` | 進場無 edge + 儀式 | 不重跑競賽；可換假說 |
| FT-004～005 | momentum / timeout cont. | MVPClosed | 見 gate | 可加 regime filter 重測 |
| FT-006/012 | VWAP stretch fade 族 | direction / fade | mean-reversion | 需本質差異或新 veto |
| FT-007 | MER flow flip | direction_weak | 弱方向 | 可測 flow 閾值 |
| FT-008/011 | breakout 族 | direction_failed | breakout | 可測 vol/session filter |
| FT-009 | ORB | train 負 | ORB | bar path + 結構 stop 可 Scout |
| FT-010/013/014 | pullback / ST / morning VWAP | fp / 稀 | 樣本或方向 | 放寬 n 契約或 bar 先篩 |
| FT-015 | FVG retest | W30≈0 | 摩擦 / 弱方向 | 可測 displacement veto |
| FT-016 | gap drive | G1 / valid− | exit_kills_edge | 進場或有方向；換 exit/filter |
| FT-017 | compression flow | n=0 | **錨點/工具** | 先修錨再談 edge |
| FT-018 | gap up drive trail | champion 無 | 近 miss → **GUDT 活線** | 延續在 FT-021/023 |
| FT-019 | sweep FVG BO trail | G1 fail | exit_kills_edge | 可測 filter 減噪 |
| FT-020 | bear streak | 未 Pick | 未跑完 | 可當 Scout |
| OSF / June | sweep·path-OK | funnel/path 負 | 工具+缺 filter 可能 | **鼓勵** bar+filter 再取樣 |

## 路徑

| 類型 | 位置 |
|------|------|
| Feature SPEC/PLAN | [`features/`](features/) |
| Workspaces / gate_report | [`../../../workspaces/_archive/`](../../../workspaces/_archive/) |
| 驗屍表 | [`../../../workspaces/_archive/CORPSE_ATLAS.md`](../../../workspaces/_archive/CORPSE_ATLAS.md) |

## 現行（不在此 archive）

- FT-001 audit · FT-021/023 GUDT · FT-022 strategy loading  
- `workspaces/RESEARCH_CHARTER_v2.md` · `gudt-*-baseline` · SessionBarCache
