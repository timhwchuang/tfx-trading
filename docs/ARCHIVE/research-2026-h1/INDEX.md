# Research archive 2026-H1（tick-era · Gen-1）

```
STATUS: ARCHIVE — prior only · SUPERSEDED by SessionBarCache era
SSOT for new research: workspaces/RESEARCH_CHARTER_v2.md
Agent: DO NOT use this tree as process template or living gate rules.
```

## 怎麼讀

| 要 | 不要 |
|----|------|
| 查「這題以前死在哪」→ 墓誌銘 | 開新 thesis 複製舊 SPEC 儀式 |
| 人主動打開 gate_report 考古 | 自動把 MVPClosed 當「永禁重測」 |
| 標 instrument_gen=1 | 逐份訂正舊結論 |

**若用 SessionBarCache 重做？** 墓誌銘預設 **否**；僅人類書面勾選才重開。

## 墓誌銘一覽

| ID | 假設（一句） | 死於 | 死因歸類 | Bar 重開？ |
|----|--------------|------|----------|------------|
| FT-002 | SMC/structure 濾網救 vwap host | CAL-8 放棄 | host 已死（非 filter 普適無效） | 否（除非新 host） |
| FT-003 | 四 agent grid 競賽救 hybrid | `grid_no_viable_solution` | 進場無 edge + 儀式過重 | 否 |
| FT-004 | momentum continuation | MVPClosed | 見 features 內 SPEC/gate | 否 |
| FT-005 | timeout continuation | MVPClosed | 同上 | 否 |
| FT-006 | VWAP stretch fade | direction_failed / net 大負 | mean-reversion 族 | 否 |
| FT-007 | MER flow flip | direction_weak | 弱方向 | 否 |
| FT-008 | short breakout | direction_failed | breakout 族 | 否 |
| FT-009 | ORB | train 負 / holdout 未過 | ORB 族 | 否（近 OR hold 故事） |
| FT-010 | VWAP trend pullback | Phase 0 未過 | 樣本/edge | 否 |
| FT-011 | session confluence BO | direction_failed | breakout 族 | 否 |
| FT-012 | regime VSF | fade 族死 | mean-reversion | 否 |
| FT-013 | SuperTrend flip | fingerprint fail W30−10 | direction_failed | 否 |
| FT-014 | morning VWAP hold PB | n=7 過稀 | 樣本不足 | 否 |
| FT-015 | FVG retest | W30 med −0 | direction_weak / 摩擦 | 否 |
| FT-016 | gap drive cont. | G1 fail / valid 負 | exit_kills_edge | 否 |
| FT-017 | compression flow | n=0 | **錨點錯** (`spec_anchor_mismatch`) | 否（先修錨） |
| FT-018 | gap up drive trail | no skew champion / valid− | 進場近 miss·出場殺 | 部分血緣 → **GUDT 現行線** |
| FT-019 | sweep FVG BO trail | fp pass · G1 fail | exit_kills_edge | 否 |
| FT-020 | bear streak flip | Draft 未 Pick | 未跑完 | 可另開，非本 archive 復活 |
| OSF | open sweep+FVG+5m | funnel 空 / June path 負 | 資料粒度+同族無 body | **預設否** |
| June path-OK | 裁量故事機械化 | soft winners=0 | 單月 / 無 family edge | 否 |

## 路徑

| 類型 | 位置 |
|------|------|
| Feature SPEC/PLAN | [`features/`](features/) |
| Workspaces / gate_report | [`../../../workspaces/_archive/`](../../../workspaces/_archive/) |
| 驗屍表 | [`../../../workspaces/_archive/CORPSE_ATLAS.md`](../../../workspaces/_archive/CORPSE_ATLAS.md) |

## 現行（不在此 archive）

- FT-001 audit · FT-021/023 GUDT · FT-022 strategy loading  
- `workspaces/RESEARCH_CHARTER_v2.md` · `gudt-*-baseline` · SessionBarCache
