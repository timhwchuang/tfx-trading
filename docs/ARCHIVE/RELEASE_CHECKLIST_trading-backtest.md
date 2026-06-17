# Release checklist — v0.1.0 (public tag)

Use this before tagging `v0.1.0` on GitHub.

## Pre-tag verification

- [ ] `python3 run_tests.py` — all tests pass (currently 25+)
- [ ] `ruff check src tests` — no lint errors
- [ ] `ruff format --check src tests` — formatted
- [x] Docs slimmed post-monorepo (releases moved to ARCHIVE/; links point to ARCHIVE where needed)
- [ ] `pyproject.toml` `Documentation` URL → `SPEC.md`
- [ ] `src/trading_backtest/_version.py` matches tag (`0.1.0`)
- [ ] `CHANGELOG.md` date and `[0.1.0]` link ready
- [ ] No committed `*.egg-info/` or `.ruff_cache/` (see `.gitignore`); remove local artifacts before tag:
  ```bash
  rm -rf src/*.egg-info .ruff_cache
  git ls-files '*.egg-info'  # should print nothing
  ```

## Dependency pin & install (current monorepo practice)

Consumers use monorepo editable or:

```bash
pip install -e packages/trading-engine
pip install -e packages/trading-backtest
```

(See root scripts/setup-dev.sh and SPEC.md §5)

Old standalone git+ examples are only in ARCHIVE/releases/.

## Tag & publish (monorepo)

```bash
git add -A
git commit -m "..."
# optional
git tag -a ...
git push origin main --tags
```

Granular release notes go under ARCHIVE/ (or omitted); document in CHANGELOG.md. See root SPEC.md §5.

## Post-tag

- [ ] GitHub Release notes (historical: were copied from docs/releases/ which are now archived)
- [ ] Verify CI green on `main` after push
- [x] Architecture references updated for monorepo (historical three-repo checklist item removed)
- [ ] Notify collaborators: **research alpha**, not production execution simulator

## Scope reminder (do not oversell)

v0.1.0 is suitable for:

- Strategy state-machine validation on the same `TradingEngine` kernel
- Determinism regression and param sweep
- Internal / collaborator research with documented limitations

v0.1.0 is **not** suitable as sole evidence for:

- Go-live decisions from backtest PnL alone
- External UAT sign-off without paper-trade fill comparison