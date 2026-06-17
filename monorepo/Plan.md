# tfx-trading Monorepo — Migration Plan

> **Spec truth**: [`SPEC.md`](SPEC.md)  
> **Review update (2026-06-17)**: strategies grouped under `packages/strategies/<name>/`

---

## Decisions (locked)

| Item | Choice |
|------|--------|
| GitHub repo | `timhwchuang/tfx-trading` |
| Git history | Fresh start (single initial migration commit) |
| Old repos | Archive only; README redirect |
| Strategy layout | **`packages/strategies/vwap-momentum/`** (not flat `packages/strategy-vwap-momentum/`) |

---

## Target tree (delta from four-repo layout)

```text
packages/trading-engine/          ← was trading-engine/
packages/trading-backtest/        ← was trading-backtest/
packages/strategies/vwap-momentum/  ← was strategy-vwap-momentum/
apps/trading-app/                 ← was trading-app/
```

---

## Phase 0 — Docs (this phase)

- [x] `monorepo/SPEC.md`
- [x] `monorepo/Plan.md`
- [ ] User creates GitHub repo `txf-trading` with Description/Topics from SPEC §8

---

## Phase 1 — Restructure directories

- [ ] Create `packages/`, `packages/strategies/`, `apps/`
- [ ] Move `trading-engine/` → `packages/trading-engine/`
- [ ] Move `trading-backtest/` → `packages/trading-backtest/`
- [ ] Move `strategy-vwap-momentum/` → `packages/strategies/vwap-momentum/`
- [ ] Move `trading-app/` → `apps/trading-app/`
- [ ] Remove nested `.git/` in each moved tree
- [ ] Remove per-package `.github/workflows/` (consolidate at root)
- [ ] Merge `.gitignore` at repo root

---

## Phase 2 — Dependencies & scripts

- [ ] Add `scripts/setup-dev.sh` (install engine, backtest, `strategies/vwap-momentum`, shioaji, PyYAML)
- [ ] Update `apps/trading-app/requirements.txt` → path `-e ../../packages/...`
- [ ] Update `apps/trading-app/scripts/ci-setup.sh` paths for new layout
- [ ] Update `apps/trading-app/run_tests.py` sibling path fallback
- [ ] Keep pyproject dependency floors (`trading-engine>=0.2.2`) — resolved via editable install

---

## Phase 3 — CI & test runner

- [ ] Update `scripts/run-all-tests.sh`:
  - `packages/trading-engine`
  - `packages/trading-backtest`
  - `packages/strategies/vwap-momentum`
  - `apps/trading-app`
  - Remove stale `theman` reference
- [ ] Add root `.github/workflows/ci.yml` (setup-dev + run-all-tests)
- [ ] Delete old four-repo workflow files (already moved/removed with nested `.github`)

---

## Phase 4 — Documentation & Windows ops

- [ ] Root `README.md` — clone `txf-trading`, `setup-dev.sh`, link to app README
- [ ] Update `apps/trading-app/docs/Architecture.md` for monorepo paths
- [ ] Mark `apps/trading-app/docs/UPGRADE_RUNBOOK.md` deprecated → `monorepo/SPEC.md` §7
- [ ] Update package README install paths (`packages/strategies/vwap-momentum`, etc.)
- [ ] Update `apps/trading-app/scripts/windows/*.ps1` if paths hardcoded
- [ ] `WeeklyStatus.md` — add migration complete section

---

## Phase 5 — Publish

- [ ] `git init` at repo root (if not already)
- [ ] Initial commit: `chore: migrate four repos into txf-trading monorepo`
- [ ] `git remote add origin git@github.com:timhwchuang/txf-trading.git`
- [ ] `git push -u origin main`
- [ ] Optional tag: `v0.3.0-monorepo` (see SPEC §7)

---

## Phase 6 — Archive old repos (after gates)

**Gates (all must pass before Archive)**

- [ ] Clean venv: `bash scripts/setup-dev.sh` OK
- [ ] `bash scripts/run-all-tests.sh` all green
- [ ] GitHub Actions green on `main`
- [ ] Windows: `apps/trading-app` live/backtest smoke documented

**Per old repo**

- [ ] Final README banner:

  ```markdown
  > **Archived.** Development moved to [txf-trading](https://github.com/timhwchuang/txf-trading).
  > Historical tags remain available; no further updates.
  ```

- [ ] Push README commit
- [ ] GitHub → Settings → Archive repository

| Repo | New path in monorepo |
|------|----------------------|
| trading-engine | `packages/trading-engine` |
| trading-backtest | `packages/trading-backtest` |
| strategy-vwap-momentum | `packages/strategies/vwap-momentum` |
| trading-app | `apps/trading-app` |

---

## Post-migration: new strategy checklist

When adding `packages/strategies/<name>/`:

1. Scaffold from `vwap-momentum`
2. Register entry point in `pyproject.toml`
3. Add `-e` line to `setup-dev.sh` and `run-all-tests.sh`
4. (Optional) app config + `load_named_strategy("<name>")`

No GitHub repo or tag coordination required.