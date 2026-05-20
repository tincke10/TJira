<p align="center">
  <img src="tjira-logo.svg" alt="TJira" width="300" />
</p>

<p align="center">
  <strong>The scissors for your Jira backlog.</strong><br>
  Cut through issues, worklogs and sprints — straight from the CLI.
</p>

<p align="center">
  <a href="https://github.com/tincke10/JiraGestionREST/actions/workflows/ci.yml"><img src="https://github.com/tincke10/JiraGestionREST/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-blue?logo=python&logoColor=white" alt="Python 3.13+" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/output-JSON-orange" alt="JSON output" />
  <img src="https://img.shields.io/badge/AI--ready-yes-blueviolet" alt="AI ready" />
  <img src="https://img.shields.io/badge/Jira-REST%20API-0052CC?logo=jira&logoColor=white" alt="Jira REST" />
</p>

---

## Why TJira?

Manage Jira from the terminal with output designed for **humans _and_ AI agents**.

- **One CLI, five verbs** — `log`, `issue`, `list`, `worklog`, `timer`. That's it.
- **Multi-account** — store as many Jira credentials as you need (`tjira profile add`), switch with one command (`tjira switch`), or override per-invocation (`tjira --profile work …`).
- **JSON-first** — add `--json` to any command and get a stable, typed envelope.
- **Script-safe** — exit codes `0/1/2`, data on stdout, logs on stderr. Pipe it into `jq`, wire it into CI, or let Claude / GPT call it as a tool.
- **Bulk-friendly** — import or wipe worklogs from CSV with a single command.
- **Timezone-aware** — configurable per environment, no more timestamp guessing.

## Quick Start

```bash
# 1. Install
pipx install .

# 2. Create your first profile (interactive — prompts for domain / email / token)
tjira profile add work

# 3. Verify your setup
tjira doctor                # validates active profile + credentials + connectivity

# 4. Go
tjira list boards
tjira log PROJ-123 2h --comment "Implemented feature X"
```

Got more than one Jira instance? Add and switch as needed:

```bash
tjira profile add personal
tjira switch personal                       # change active profile
tjira --profile work list issues --json     # one-shot override
```

## Installation

<table>
<tr>
<th>Option</th>
<th>Command</th>
<th>When to use</th>
</tr>
<tr>
<td><b>pipx</b></td>
<td><code>pipx install .</code></td>
<td>Recommended — isolated, global <code>tjira</code> binary</td>
</tr>
<tr>
<td><b>pip (editable)</b></td>
<td><code>pip install -e .</code></td>
<td>Local development — edit source, see changes instantly</td>
</tr>
<tr>
<td><b>Module mode</b></td>
<td><code>python -m tjira ...</code></td>
<td>No install needed, just <code>pip install typer requests tomli-w</code></td>
</tr>
</table>

> **Note:** Requires Python 3.13 or newer. On macOS, `brew install python@3.14`. On Debian/Ubuntu, `apt install python3.14 python3.14-venv`. Then use `python3.14 -m pip install -e .` (or `pipx install .`).

## Configuration

Credentials live in a TOML file at `$XDG_CONFIG_HOME/tjira/config.toml`
(defaults to `~/.config/tjira/config.toml`). The file is created automatically
the first time you run `tjira profile add`, and is written with `0600`
permissions so other users on the host cannot read your tokens.

### Add your first profile

```bash
tjira profile add work        # prompts interactively for domain / email / token
```

Or non-interactively:

```bash
tjira profile add work \
  --domain your-company.atlassian.net \
  --email you@your-company.com \
  --token "$(cat ~/secrets/jira-token)"
```

> **Security note:** `--token X` exposes the token to your shell history and
> the system process list (`ps`). For interactive use prefer plain
> `tjira profile add work` (the prompt masks the token and never reaches argv).
> For automation, read the token from a file or pipe it via the
> `JIRA_API_TOKEN` env var + `--from-env`.

Get your API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.

### Migrate from `.env`

If you previously used `JIRA_DOMAIN/EMAIL/API_TOKEN` env vars or a `.env`
file, source those values once and then:

```bash
export $(grep -v '^#' .env | xargs)         # if you still have a .env
tjira profile add default --from-env
```

### Multiple profiles

```bash
tjira profile add personal                 # add a second one
tjira profile list                         # see them all (active marked with *)
tjira profile current                      # print just the active name
tjira switch personal                      # change active
tjira --profile work list issues --json    # one-shot override (warns on stderr)
tjira profile rm personal                  # remove (prompts unless --yes)
```

### Optional environment variables

These are still read from the environment because they are operational, not
credential-based:

```env
JIRA_TIMEZONE=America/Argentina/Buenos_Aires   # defaults to system local
JIRA_TIMEOUT=30                                # HTTP timeout in seconds
```

### Profile file shape

```toml
current_profile = "work"

[profiles.work]
domain = "your-company.atlassian.net"
email = "you@your-company.com"
api_token = "ATATT..."

[profiles.personal]
domain = "personal.atlassian.net"
email = "you@gmail.com"
api_token = "ATATT..."
```

## Commands

All commands accept `--json` for machine output. Without it, you get a clean human table.

### `tjira doctor` — health check

Validates your setup end-to-end. Great for first-run onboarding and CI smoke tests.

```bash
tjira doctor              # human-friendly table of checks
tjira doctor --json       # machine-readable for agents / automation
```

Checks performed:

- An active profile is configured and resolvable (`tjira profile current`)
- `profile.domain` has a plausible shape (host-only, no scheme, no trailing slash)
- `JIRA_TIMEZONE` is a valid IANA timezone (if set)
- Live `GET /myself` call to verify credentials actually work

Exits `0` when every check passes, `1` otherwise — perfect as a preflight step in scripts.

### `tjira log` — single worklog

```bash
tjira log PROJ-123 2h
tjira log PROJ-123 "1h 30m" "2026-04-20"
tjira log PROJ-123 45m "2026-04-20 09:00" --comment "Bug fix" --json
```

### `tjira issue` — CRUD + transitions

```bash
tjira issue get PROJ-123                         # detail view
tjira issue create PROJ "Implement feature X"    # create Task
tjira issue create PROJ "Fix login" --type Bug --desc "Steps to reproduce..."
tjira issue create PROJ "Implement login" --parent PROJ-5 --type Task   # link to Epic on creation
tjira issue update PROJ-123 --summary "New title"
tjira issue update PROJ-123 --status "In Progress"
tjira issue update PROJ-123 --assign me
tjira issue update PROJ-123 --comment "Done" --attach screenshot.png
tjira issue update PROJ-123 --parent EPIC-7     # move issue under an Epic
tjira issue update PROJ-123 --parent NONE        # detach from its current parent
tjira issue transitions PROJ-123 --json          # available status changes
```

**`--parent / -P`** accepts an Epic key (e.g. `PROJ-5`) to link the issue on creation or move it to a
different Epic on update. Pass the literal string `NONE` to clear the parent relationship entirely.

> **Classic Jira projects:** The `--parent` flag uses the next-gen parent field. Classic projects
> that rely on `customfield_10014` (Epic Link) are not supported — the CLI will surface a clear
> error message if it detects this situation.

### `tjira list` — search & discovery

```bash
tjira list issues                                         # my open issues
tjira list issues --project PROJ --json
tjira list issues --jql "project = PROJ AND created >= -7d" --limit 50

tjira list boards --project PROJ
tjira list sprints 365
tjira list sprint-issues 1234 --json
tjira list board-issues 365 --json

tjira list filters
tjira list filter-issues 10042 --json
tjira list dashboards
```

#### Discovery commands

These four commands help you explore a Jira project before creating issues or building
automation scripts. They are read-only and always accept `--json`.

```bash
# List accessible projects (paginated, optional type filter)
tjira list projects --json
tjira list projects --limit 100 --type software --json

# Discover issue types available in a project
tjira list issue-types PROJ --json

# Search Jira users by name fragment (useful for --assign values)
tjira list users "john" --json
tjira list users "john" --limit 100

# Discover fields for a specific issue type in a project
# Returns required and optional fields with allowed values
tjira list fields PROJ Task --json
tjira list fields PROJ Task --required-only --json     # only required fields
tjira list fields PROJ Story --limit 200 --json        # increase field limit
```

All discovery commands emit a JSON array to stdout with typed, normalized shapes:

| Command | Output shape |
| ------- | ------------ |
| `list projects` | `{"key", "name", "type", "style"}` |
| `list issue-types` | `{"id", "name", "subtask": bool, "description"}` |
| `list users` | `{"account_id", "display_name", "email" \| null, "active": bool}` |
| `list fields` | `{"name", "key", "required": bool, "type", "allowed_values": list \| null}` |

### `tjira worklog` — bulk CSV ops

```bash
tjira worklog import worklogs.csv --dry-run       # preview
tjira worklog import worklogs.csv --json          # import
tjira worklog delete worklogs.csv --dry-run       # preview deletion
```

See [ESTRUCTURA_CSV.md](ESTRUCTURA_CSV.md) for the CSV schema.

### `tjira profile` & `tjira switch` — manage Jira accounts

```bash
tjira profile add work                  # interactive prompts
tjira profile add personal --from-env   # migrate from JIRA_DOMAIN/EMAIL/API_TOKEN
tjira profile list                      # active is marked with *
tjira profile list --json               # machine-readable (no tokens in payload)
tjira profile current                   # parseable single line
tjira profile rm personal --yes         # remove (skip confirmation)

tjira switch personal                   # change active profile
tjira --profile work list issues        # one-shot override; warns on stderr
```

### `tjira timer` — time tracking

Track time spent on issues without leaving the terminal. Start a timer when you
begin work, stop it when you are done — the elapsed time is automatically
rounded to the nearest minute and posted as a Jira worklog.

```bash
# Start a timer for an issue (stores start time locally; no network call)
tjira timer start PROJ-123
tjira timer start PROJ-123 --comment "Implementing auth"

# Check the running timer
tjira timer status
tjira timer status --json

# Stop the timer and post a worklog (runs overlap pre-check by default)
tjira timer stop
tjira timer stop --json
tjira timer stop --force            # skip overlap pre-check

# Discard the timer without posting a worklog
tjira timer cancel
tjira timer cancel --json
```

**Flags:**

| Flag | Command | Description |
| ---- | ------- | ----------- |
| `--comment "..."` | `start` | Worklog comment; stored and applied when you run `stop` |
| `--force` | `stop` | Skip the overlap pre-check (does NOT bypass the cross-profile safeguard) |
| `--json` | all | JSON envelope on stdout |

**Exit codes for `timer stop`:** `0` OK · `1` no active timer or cross-profile
mismatch · `2` Jira API error (timer file preserved for retry) · `3` overlap detected.

**State file:** `$XDG_CONFIG_HOME/tjira/timer.json` (fallback `~/.config/tjira/timer.json`),
written atomically with `0600` permissions. A single timer is supported at a time.

**Known v1 limitations:**
- Concurrent `tjira` processes racing on `timer.json` is last-write-wins (single-user, single-machine use case).
- `--force` scoped strictly to the overlap pre-check; cross-profile mismatch always requires an explicit `tjira switch <profile>` or `tjira timer cancel`.

#### Claude Code integration

TJira ships a Claude Code hook that auto-manages the timer for you. When you
open Claude Code in a repository on a Jira-tagged branch (`feat/PROJ-123-...`,
`fix/PROJ-123`, etc.) the hook starts a timer automatically. When your Claude
session ends (`Stop` event) it stops the timer and posts the worklog.

**How it works:**

1. Claude Code invokes `.claude/hooks/tjira-timer-hook.sh SessionStart` on session open.
2. The script reads `cwd` from the hook's stdin JSON, resolves the current git branch, and extracts the issue key via the pattern `(feat|fix|chore|refactor|test|docs)/PROJ-123[-_/...]`.
3. If no timer is currently active it calls `tjira timer start <KEY>`.
4. On session end (`Stop`) it calls `tjira timer stop --json`, posting the elapsed worklog.

**Install (project-level — already done):**

The hook is pre-configured in `.claude/settings.json` at the repo root. No
action needed; it fires automatically for anyone with `tjira` on PATH when they
open Claude Code in this repository.

**Promote to user-global (optional):**

If you want the hook to fire for **all** your projects, copy the hook config
into your user-level Claude settings:

```bash
# Merge SessionStart + Stop entries into ~/.claude/settings.json
# (create the file if it does not exist)
cat .claude/settings.json >> ~/.claude/settings.json
# Then edit ~/.claude/settings.json to deduplicate if you already had hooks.
```

> **Warning:** A user-global hook invokes `tjira` on every Claude session start
> in every directory. The branch-name regex will filter most calls, but `tjira`
> still runs. Accept this only if you work primarily on Jira projects.

**Requirements:**

- `tjira` must be on `PATH` when Claude Code launches. Install globally with
  `pipx install .` or activate the project venv before launching Claude.
- If `tjira` is not found the hook exits 0 silently — it never blocks your session.

**Branch naming convention:**

The hook recognises branches that match:

```
(feat|fix|chore|refactor|test|docs)/<PROJECT>-<NUMBER>[-_/<rest>]
```

Examples that trigger the hook: `feat/PROJ-123`, `fix/PROJ-42-login-bug`,
`chore/MYAPP-7_update-deps`.

Examples that do NOT trigger: `main`, `develop`, `hotfix/some-fix` (no issue key).

## Shell Completion

Tab-completion is built in (courtesy of Typer). Install it once per shell:

```bash
tjira --install-completion          # auto-detect current shell (bash/zsh/fish/powershell)
```

Then restart your shell and enjoy `tjira l<TAB>` → `log`, `list`. To preview the
completion script without installing, run `tjira --show-completion`.

## Output Contract

| Stream       | Contents                                                         |
| ------------ | ---------------------------------------------------------------- |
| `stdout`     | Data — either a human table or a JSON envelope                   |
| `stderr`     | Progress logs, or `{"ok": false, "error": ...}` on failure       |
| Exit `0`     | Success                                                          |
| Exit `1`     | User error (bad args, missing env, invalid date…)                |
| Exit `2`     | Jira/API error (network, 4xx, 5xx)                               |
| Exit `3`     | Worklog overlap detected (`tjira log` / `tjira timer stop`)      |

**JSON envelope on success:**

```json
{ "ok": true, "data": { "...": "..." } }
```

## Using TJira with AI Agents

Because every command speaks JSON and respects exit codes, any LLM tool-use loop can call it safely:

```bash
result=$(tjira list issues --project PROJ --json)
if [ $? -eq 0 ]; then
  echo "$result" | jq '.data.issues[] | {key, status, summary}'
fi
```

Perfect for Claude Code tool definitions, GPT function-calling, or agent-style CI jobs.

## Project Structure

```
TJira/
├── tjira/                    # Unified CLI package
│   ├── cli.py                # Typer app + dashboard view + --profile flag
│   ├── client.py             # Jira REST client (APIError on failures)
│   ├── config.py             # Active-profile resolution + override plumbing
│   ├── profiles.py           # Profile dataclass + TOML-backed ProfileStore
│   ├── timer.py              # TimerState + TimerStore (atomic, XDG-aware)
│   ├── overlap.py            # Overlap detection + format_time_spent helper
│   ├── errors.py             # Exit codes + typed exceptions
│   ├── formatters.py         # Human/JSON output normalizers
│   ├── tz.py                 # Timezone-aware datetimes
│   └── commands/
│       ├── doctor.py         # tjira doctor
│       ├── log.py            # tjira log
│       ├── issue.py          # tjira issue {get,create,update,transitions}
│       ├── list_cmd.py       # tjira list {issues,boards,sprints,...}
│       ├── worklog.py        # tjira worklog {import,delete}
│       ├── profile.py        # tjira profile {add,list,current,rm}
│       ├── switch.py         # tjira switch <name>
│       └── timer.py          # tjira timer {start,stop,status,cancel}
│
├── .claude/
│   ├── settings.json         # Claude Code hook registration (project-level)
│   └── hooks/
│       └── tjira-timer-hook.sh   # POSIX sh hook — auto-manages timer on SessionStart/Stop
│
├── tests/                    # pytest suite (config, profiles, client, CLI, tz, formatters)
├── legacy/                   # Pre-unification scripts (deprecated, still work)
├── .github/workflows/ci.yml  # Lint (ruff) + tests (py3.13/3.14)
│
├── pyproject.toml            # Packaging + entry point + ruff/pytest config
├── README.md
├── CHANGELOG.md
├── LICENSE                   # MIT
├── ESTRUCTURA_CSV.md         # CSV schema for bulk worklog ops
├── tjira-logo.svg            # Banner logo (with wordmark)
└── tjira-icon.svg            # Square app icon
```

## Legacy Scripts

The original standalone scripts (`log_hours.py`, `create_task.py`, etc.) have
moved to [`legacy/`](legacy/) and remain fully functional for backwards
compatibility. New code and users should prefer `tjira`. See
[`legacy/README.md`](legacy/README.md) for the full mapping and migration
guide.

```bash
python legacy/log_hours.py PROJ-123 2h         # still works
python legacy/create_task.py PROJ "New task"   # still works
```

## Development

```bash
# Clone and install with dev deps
git clone https://github.com/tincke10/JiraGestionREST.git
cd JiraGestionREST
pip install -e ".[dev]"

# Run the test suite (mocked HTTP, no real Jira calls)
pytest

# Lint
ruff check .
```

CI runs `ruff check` and `pytest` on Python 3.13 and 3.14 for every push
and pull request — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes (and run `ruff check .` before committing)
4. Submit a pull request

## License

**MIT** — do whatever you want, just don't blame us if your timesheets look weird.

---

<p align="center">
  <sub>Built with <a href="https://typer.tiangolo.com">Typer</a> · Talks to Jira via REST · Made for humans and robots alike.</sub>
</p>
