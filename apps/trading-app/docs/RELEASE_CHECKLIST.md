# Release checklist — trading-app

> **現行發布**：見 monorepo 根 [`monorepo/SPEC.md`](../../../monorepo/SPEC.md) §7。本檔保留**舊四-repo** 機械檢查紀錄。

## v0.1.2 — completed 2026-06-17

- [x] Sibling tags: `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- [x] `python run_tests.py` — 81 OK (app); engine 80 + strategy 33 OK
- [x] P4-13 config + `UPGRADE_RUNBOOK.md`
- [x] `requirements.txt` pins `@v0.2.2` / `@v0.1.2`
- [x] `git push origin main && git push origin v0.1.2`

---

## v0.1.1 — completed 2026-06-16

- [x] Sibling tags: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`
- [x] `python run_tests.py` — 79 OK (app); siblings 27 + 31 OK
- [x] Remove `theman_*` aliases; ops docs → `trading-app`
- [x] `requirements.txt` pins `@v0.1.1`
- [x] `git push origin main && git push origin v0.1.1`

---

## v0.1.0 — reference (completed 2026-06-16)

Use this before tagging `v0.1.0` on GitHub.

## Pre-tag verification

- [ ] `python run_tests.py` — all tests pass (~30 integration tests)
- [ ] `ruff check src tests` — no lint errors (if ruff installed)
- [x] Post-monorepo docs slim: releases/ archived; links and stubs cleaned (see root DOC_MAP)
- [ ] `pyproject.toml` version = `0.1.0`
- [ ] `CHANGELOG.md` date and `[0.1.0]` link ready
- [ ] `config/config.yaml` → `simulation: true`
- [ ] No committed `.env`, `*.pfx`, API keys
- [ ] No `from theman` / no re-export shim imports in `src/`

## Code review gate (required before tag)

- [ ] Run `/review` on full PR-1 + PR-2 diff
- [ ] Code review via `/review` or GitHub PR review (conclusions → `WeeklyStatus.md`)
- [ ] **0 high-severity issues** (medium/low documented or fixed)
- [ ] Re-run `python run_tests.py` after review fixes

## Dependency pins & install (current monorepo practice)

```bash
cd /path/to/tfx-trading
bash scripts/setup-dev.sh   # editable installs from packages/
# or for a consuming environment:
pip install -e packages/trading-engine
pip install -e packages/trading-backtest
pip install -e packages/strategies/vwap-momentum
pip install -r apps/trading-app/requirements.txt
```

Old standalone `git+` pins are in ARCHIVE/releases/ only (pre-monorepo).

## Tag and publish (monorepo)

```bash
git add -A
git commit -m "Release vX.Y.Z: ..."
# Optional monorepo integration tag
git tag -a v2026.06.XX-monorepo -m "..."
git push origin main
git push origin --tags
```

See monorepo/SPEC.md §7 for current release SOP. No new docs/releases/ files — use CHANGELOG.md.

## Post-tag

- [ ] GitHub Release notes (pre-monorepo; releases/ content now in ARCHIVE)
- [ ] CI green on `main`
- [x] Docs consolidated to monorepo root (pre-monorepo three-repo checklist cleaned)
- [ ] Begin UAT per `docs/UAT_CHECKLIST.md`

## Scope reminder

v0.1.0 is suitable for:

- Windows simulation UAT with tick archive + `uat_report`
- Reference wiring for custom integrator apps

v0.1.0 is **not** suitable as sole evidence for live / Pilot Go — Phase 6 calibration still required.