# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tjira doctor` command to validate environment, credentials, and timezone config.
- Shell completion docs (`tjira --install-completion`).
- Unit tests under `tests/` covering config, client, formatters, and CLI smoke.
- GitHub Actions CI running `ruff check` + `pytest`.
- `LICENSE` (MIT), `.env.example`, and this `CHANGELOG.md`.

### Changed
- **BREAKING:** minimum Python bumped from 3.9 → **3.13**. Older versions are EOL or in security-only mode as of April 2026.
- CI matrix updated to Python 3.13 and 3.14 (only actively-supported versions).
- GitHub Actions upgraded: `actions/checkout@v6`, `actions/setup-python@v6` (Node 24 runtime).
- Dependencies bumped to latest stable: `requests>=2.32.5`, `python-dotenv>=1.2.1`, `typer>=0.23.2`, `pytest>=8.4.2`, `responses>=0.26.0`, `ruff>=0.15.0`.
- `ruff` target version upgraded to `py313`.
- README redesigned for clarity: banner, badges, quickstart, output contract.
- Legacy standalone scripts moved to `legacy/` (still functional, kept for backwards compatibility).
- `.gitignore` extended to cover packaging, test caches, and OS cruft.

### Removed
- Support for Python 3.9, 3.10, 3.11, 3.12 (no longer tested in CI).
- Old `logo.svg` — replaced by `tjira-logo.svg` and `tjira-icon.svg`.

## [0.1.0] — 2026-04-20

### Added
- Unified CLI `tjira` with subcommands:
  - `log` — register a worklog on an issue
  - `issue` — CRUD + transitions (`get`, `create`, `update`, `transitions`)
  - `list` — search issues, boards, sprints, filters, dashboards
  - `worklog` — bulk import/delete from CSV
- `--json` flag on every command for machine-readable output.
- Standard exit codes: `0` OK, `1` user error, `2` API error.
- Output contract: data on stdout, logs on stderr.
- Timezone-aware worklog handling via `JIRA_TIMEZONE`.
- Typed `APIError` propagation from the REST client.

[Unreleased]: https://github.com/tincke10/JiraGestionREST/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tincke10/JiraGestionREST/releases/tag/v0.1.0
