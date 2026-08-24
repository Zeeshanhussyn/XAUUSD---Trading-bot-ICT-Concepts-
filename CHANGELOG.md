# Changelog

All notable changes to this project are logged here, newest first.

## 2026-08-24 — Work Package 1: Project Scaffold

- Created clean project folder structure: `data/`, `src/xauusd_research/`, `tests/`, `config/`,
  `scripts/`, `results/`.
- Installed `pytest` and `pyarrow` (free, open-source) in the research environment.
- Created governance files: `README.md`, `CHANGELOG.md`, `RESEARCH_DECISIONS.md`,
  `MASTER_PROGRESS_TRACKER.md`, `TRIAL_LOG.csv`, `.gitignore`, `requirements.txt`.
- Initialized `src/xauusd_research` as a minimal Python package (`__init__.py` only — feature
  code will be added in the work packages that implement it, not before).
- Initialized local Git repository, first commit.
- Connected a folder on the user's Windows desktop (`Desktop\XAUUSD_Research`) so the project
  persists outside the cloud session; GitHub remote pending (Personal Access Token requested from
  user, not yet provided).

## 2026-08-24 — Work Package 0: Environment Audit

- Confirmed cloud research environment: Python 3.11.15, Git 2.43.0, Node 22.22.2, pandas 3.0.2,
  numpy 2.4.4, scipy 1.17.1, matplotlib 3.10.9 already present; ~30GB free disk.
- Confirmed no MetaTrader5 python package available (expected — MT5 is Windows-only, this sandbox
  is Linux). No broker/MT5 access from the cloud sandbox.
- Confirmed desktop bridge available to user's Windows device; no folder connected yet at audit
  time.
- Recommended Sonnet 5 (session default) as sufficient for this routine audit.
