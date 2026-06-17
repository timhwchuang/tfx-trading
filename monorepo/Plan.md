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
- [x] GitHub repo `tfx-trading` created

---

## Phase 1 — Restructure directories

- [x] Create `packages/`, `packages/strategies/`, `apps/`
- [x] Move trees; remove nested `.git/`
- [x] Consolidate CI at root; merge `.gitignore`

---

## Phase 2 — Dependencies & scripts

- [x] `scripts/setup-dev.sh` (auto `.venv`)
- [x] Path editable `requirements.txt`
- [x] `ci-setup.sh`, `run_tests.py` paths

---

## Phase 3 — CI & test runner

- [x] `scripts/run-all-tests.sh` (four suites, no `theman`)
- [x] Root `.github/workflows/ci.yml`

---

## Phase 4 — Documentation & Windows ops

- [x] Root `README.md`, `SPEC.md`, `docs/Architecture.md`, `docs/DOC_MAP.md`
- [x] App Architecture stub → root; UPGRADE_RUNBOOK deprecated
- [x] `WeeklyStatus.md` migration section
- [x] Windows `.ps1` paths → `-MonorepoRoot C:\tfx-trading`

---

## Phase 5 — Publish

- [x] `git init`, initial commit `39b6c2d`
- [x] `git push origin main` → `timhwchuang/tfx-trading`
- [x] Optional tag: `v0.3.0-monorepo`（遷移里程碑；非每日必需）

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
  > **Archived.** Development moved to [tfx-trading](https://github.com/timhwchuang/tfx-trading).
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