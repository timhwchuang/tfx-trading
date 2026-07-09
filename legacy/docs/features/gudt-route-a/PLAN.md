---
id: FT-021
slug: gudt-route-a
status: Draft
opened: 2026-06-30
phases: [0, 1, 2, 3, 4, 5]
blockers: []
---

# FT-021 — GUDT Route A UAT Stack（PLAN）

> **PLAN** = 怎麼交付 SPEC。Phase checkbox 隨 PR 更新。

## Scope

- `strategy-gudt-route-a` plugin（entry `gudt_route_a`）
- `ft021_run_baseline.py` + `workspaces/gudt-route-a-baseline/`
- `ft021_parity_check.py`（CF oracle vs kernel）
- Bugbot ≤3 輪

## Out of scope

- Live UAT 切換
- B′ champion 替換
- 參數 tune

## Phases

### Phase 0 — 文件

- [ ] `docs/features/gudt-route-a/SPEC.md`
- [ ] `docs/features/gudt-route-a/PLAN.md`
- [ ] `docs/features/README.md` FT-021 列
- [ ] `docs/DOC_MAP.md` · `CHANGELOG.md`

### Phase 1 — Package scaffold

- [ ] `packages/strategies/gudt-route-a/`（pyproject、params、replay、stack types）
- [ ] `strategy_gudt_route_a/stack.py`（port from `gudt_route_a_stack.py`）
- [ ] `strategy_gudt_route_a/route_a_exit.py`（port from reporting）
- [ ] unit tests（router、confirm、replay smoke）

### Phase 2 — Strategy + wiring

- [ ] `GudtRouteAStrategy`（replay state machine）
- [ ] `engine_wiring.py` + config keys
- [ ] `integrations/gudt_replay_planner.py`（CF → replay events）

### Phase 3 — Baseline

- [ ] `ft021_run_baseline.py`
- [ ] `workspaces/gudt-route-a-baseline/config/config.yaml`

### Phase 4 — Parity

- [ ] `ft021_parity_check.py`
- [ ] 全期 2025-05..2026-06 對帳

### Phase 5 — Bugbot

- [ ] Round 1–3 review/fix；whack-a-mole → `REVIEW.md`

**Gate**：Phase 0 審閱 → Phase 1 開工。

## Acceptance

- [ ] SPEC §5 Definition of Done 全勾
- [ ] `bash scripts/run-all-tests.sh` 全綠

## Risks

| 風險 | 緩解 |
|------|------|
| reporting ↔ plugin 漂移 | stack port 至 strategy；CF import shared |
| fill 模型差 | SPEC ±15 pts；決策層與 PnL 層分開對帳 |

## Reproduce

```bash
cd apps/trading-app/src
PYTHONPATH=. python scripts/ft018_gudt_route_a_stack.py --from 2025-05-01 --to 2026-06-30
PYTHONPATH=. python scripts/ft021_run_baseline.py --from 2025-05-01 --to 2026-06-30
PYTHONPATH=. python scripts/ft021_parity_check.py --from 2025-05-01 --to 2026-06-30
```
