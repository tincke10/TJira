# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tjira doctor` command to validate environment, credentials, and timezone config.
- Shell completion docs (`tjira --install-completion`).
- Unit tests under `tests/` covering config, client, formatters, and CLI smoke.
- GitHub Actions CI running `ruff check` + `pytest` on Python 3.9–3.12.
- `LICENSE` (MIT), `.env.example`, and this `CHANGELOG.md`.

### Changed
- README redesigned for clarity: banner, badges, quickstart, output contract.
- Legacy standalone scripts moved to `legacy/` (still functional, kept for backwards compatibility).
- `.gitignore` extended to cover packaging, test caches, and OS cruft.

### Removed
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
