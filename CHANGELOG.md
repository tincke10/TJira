# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tjira timer start <ISSUE> [--comment]` — start a worklog timer. Stores start time, profile, and optional comment in `$XDG_CONFIG_HOME/tjira/timer.json` (mode `0600`). Raises `UserError` (exit 1) if a timer is already active.
- `tjira timer stop [--force]` — stop the timer and post a worklog with the elapsed time (rounded to the nearest minute via `format_time_spent`). Runs an overlap pre-check before posting; `--force` bypasses the overlap check only (cross-profile safeguard is always enforced). Exit 2 on API error preserves the state file for retry.
- `tjira timer status` — show the running timer (issue key, elapsed, started_at) or empty state. `--json` returns `{"ok": true, "data": null}` when no timer is active.
- `tjira timer cancel` — discard the timer without posting a worklog (idempotent; exit 0 when no timer is active).
- `format_time_spent(td)` helper in `tjira.overlap` — converts a `timedelta` to a Jira-style string (`"1h 30m"`, `"45m"`, etc.) using banker's rounding, clamped to a minimum of `"1m"`. Symmetric to `parse_time_spent`.
- **Claude Code integration** via `.claude/hooks/tjira-timer-hook.sh` + `.claude/settings.json` — auto-starts the timer when opening Claude Code on a Jira-tagged branch (`feat/PROJ-123-...`, `fix/PROJ-42`, etc.) and stops it on session end. Hook is POSIX `sh`, always exits 0, and is a no-op when `tjira` is not on PATH.
- `tjira issue create --parent / -P <EPIC-KEY>` to link a new issue to an Epic on creation.
- `tjira issue update --parent <EPIC-KEY|NONE>` to re-parent or clear the parent of an existing issue. Pass the literal string `NONE` to detach the issue from its current Epic.
- `tjira list projects` — list accessible Jira projects with `--limit` (default 50, max 1000) and `--type` filtering (e.g. `software`, `service_desk`, `business`).
- `tjira list issue-types <project>` — discover issue types available in a project (e.g. Task, Bug, Story, Epic) using the modern createmeta endpoint.
- `tjira list users <query>` — search Jira users by name fragment, with `--limit` and `--json` support. Email is `null` for privacy-restricted accounts.
- `tjira list fields <project> <issue-type>` — discover fields (required and optional) for a create context, with `--required-only` filter and `--limit`. Performs a two-roundtrip flow: resolves the issue type name to an ID, then fetches its fields.
- **Classic-project interception.** When Jira rejects a `--parent` operation because the project uses the legacy Epic Link field (`customfield_10014`), the CLI surfaces a clear `UserError` (exit 1) with a hint instead of a raw 400, and preserves the original Jira error under `"original_error"` in the JSON payload.
- **Multi-profile support.** Multiple Jira instances can be managed from a single CLI:
  - `tjira profile add <name>` — create a profile (interactive prompts when no flags given, or `--domain/--email/--token` for non-interactive use).
  - `tjira profile add <name> --from-env` — migrate from existing `JIRA_DOMAIN/EMAIL/API_TOKEN` env vars into a named profile.
  - `tjira profile list` — show all profiles, the active one is marked with `*`. `--json` for machine-readable output.
  - `tjira profile current` — print the active profile name (parseable single line).
  - `tjira profile rm <name>` — remove a profile (prompts for confirmation, `--yes` to skip).
  - `tjira switch <name>` — change the active profile.
  - Global `--profile <name>` / `-p` flag — override the active profile for a single invocation; prints `[Using profile: X]` to stderr when it differs from the stored active.
- **Dashboard view.** `tjira` (no subcommand) now shows the active profile, domain, email, and other-profile count. When no profile is configured and the shell is interactive, offers to set one up inline.
- TOML credential store at `$XDG_CONFIG_HOME/tjira/config.toml` (defaults to `~/.config/tjira/config.toml`), written atomically with `0600` permissions. The leaf directory is also locked to `0700` so the file's existence is hidden from other users.

### Security
- **Domain validation** at every credential entry point (`profile add` flags, interactive prompts, `--from-env`, dashboard onboarding) rejects URL-looking strings, paths, query strings, fragments, userinfo, and whitespace. Without this, a domain like `real.atlassian.net@evil.com` would route the API token to the attacker's host because of URL parsing rules.
- **Profile name validation** restricts names to `[A-Za-z0-9._-]` starting with an alphanumeric character, blocking empty/control-char/path-traversal-looking inputs.
- `profile list --json` deliberately omits `api_token` from its payload (covered by tests).
- `tjira doctor` command to validate environment, credentials, and timezone config.
- Shell completion docs (`tjira --install-completion`).
- Unit tests under `tests/` covering config, client, formatters, and CLI smoke.
- GitHub Actions CI running `ruff check` + `pytest`.
- `LICENSE` (MIT), `.env.example`, and this `CHANGELOG.md`.

### Changed
- **BREAKING:** credentials are no longer read from environment variables or `.env` files. The CLI now reads exclusively from the TOML profile store. Existing users must run `tjira profile add <name> --from-env` once (with the legacy vars exported) to migrate.
- **BREAKING:** minimum Python bumped from 3.9 → **3.13**. Older versions are EOL or in security-only mode as of April 2026.
- `tjira doctor` rewrote its checks around the active profile (`profile`, `domain_shape`, `timezone`, `jira_connectivity`) instead of raw env vars.
- CI matrix updated to Python 3.13 and 3.14 (only actively-supported versions).
- GitHub Actions upgraded: `actions/checkout@v6`, `actions/setup-python@v6` (Node 24 runtime).
- Dependencies bumped to latest stable: `requests>=2.32.5`, `typer>=0.23.2`, `pytest>=8.4.2`, `responses>=0.26.0`, `ruff>=0.15.0`.
- `ruff` target version upgraded to `py313`.
- README redesigned for clarity: banner, badges, quickstart, output contract.
- Legacy standalone scripts moved to `legacy/` (still functional, kept for backwards compatibility).
- `.gitignore` extended to cover packaging, test caches, and OS cruft.

### Removed
- **BREAKING:** `python-dotenv` dependency. `.env` is no longer parsed by the CLI — use profiles instead. Legacy scripts under `legacy/` now read credentials from the process environment only; users with a `.env` must source it manually (`set -a && . ./.env && set +a`) before running them.
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
