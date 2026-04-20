<p align="center">
  <img src="tjira-logo.svg" alt="TJira" width="300" />
</p>

<p align="center">
  <strong>The scissors for your Jira backlog.</strong><br>
  Cut through issues, worklogs and sprints — straight from the CLI.
</p>

<p align="center">
  <a href="https://github.com/tincke10/JiraGestionREST/actions/workflows/ci.yml"><img src="https://github.com/tincke10/JiraGestionREST/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white" alt="Python 3.9+" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/output-JSON-orange" alt="JSON output" />
  <img src="https://img.shields.io/badge/AI--ready-yes-blueviolet" alt="AI ready" />
  <img src="https://img.shields.io/badge/Jira-REST%20API-0052CC?logo=jira&logoColor=white" alt="Jira REST" />
</p>

---

## Why TJira?

Manage Jira from the terminal with output designed for **humans _and_ AI agents**.

- **One CLI, four verbs** — `log`, `issue`, `list`, `worklog`. That's it.
- **JSON-first** — add `--json` to any command and get a stable, typed envelope.
- **Script-safe** — exit codes `0/1/2`, data on stdout, logs on stderr. Pipe it into `jq`, wire it into CI, or let Claude / GPT call it as a tool.
- **Bulk-friendly** — import or wipe worklogs from CSV with a single command.
- **Timezone-aware** — configurable per environment, no more timestamp guessing.

## Quick Start

```bash
# 1. Install
pipx install .

# 2. Configure — copy the template and fill it in
cp .env.example .env        # then set JIRA_DOMAIN / JIRA_EMAIL / JIRA_API_TOKEN

# 3. Verify your setup
tjira doctor                # validates env + credentials + connectivity

# 4. Go
tjira list boards
tjira log PROJ-123 2h --comment "Implemented feature X"
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
<td>No install needed, just <code>pip install typer requests python-dotenv</code></td>
</tr>
</table>

> **Note:** editable installs require `pip >= 21.3` (PEP 660). Upgrade with `python -m pip install --upgrade pip` if needed.

## Configuration

1. Grab your Jira API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. Create a `.env` file in the project root:

```env
# Required
JIRA_DOMAIN=your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_api_token_here

# Optional
JIRA_TIMEZONE=America/Argentina/Buenos_Aires   # defaults to system local
JIRA_TIMEOUT=30                                # HTTP timeout in seconds
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

- `.env` and required vars (`JIRA_DOMAIN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`) present
- `JIRA_DOMAIN` has a plausible shape (host-only, no scheme, no trailing slash)
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
tjira issue update PROJ-123 --summary "New title"
tjira issue update PROJ-123 --status "In Progress"
tjira issue update PROJ-123 --assign me
tjira issue update PROJ-123 --comment "Done" --attach screenshot.png
tjira issue transitions PROJ-123 --json          # available status changes
```

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

### `tjira worklog` — bulk CSV ops

```bash
tjira worklog import worklogs.csv --dry-run       # preview
tjira worklog import worklogs.csv --json          # import
tjira worklog delete worklogs.csv --dry-run       # preview deletion
```

See [ESTRUCTURA_CSV.md](ESTRUCTURA_CSV.md) for the CSV schema.

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
│   ├── cli.py                # Typer app + entry point
│   ├── client.py             # Jira REST client (APIError on failures)
│   ├── config.py             # Env validation
│   ├── errors.py             # Exit codes + typed exceptions
│   ├── formatters.py         # Human/JSON output normalizers
│   ├── tz.py                 # Timezone-aware datetimes
│   └── commands/
│       ├── doctor.py         # tjira doctor
│       ├── log.py            # tjira log
│       ├── issue.py          # tjira issue {get,create,update,transitions}
│       ├── list_cmd.py       # tjira list {issues,boards,sprints,...}
│       └── worklog.py        # tjira worklog {import,delete}
│
├── tests/                    # pytest suite (config, client, CLI, tz, formatters)
├── legacy/                   # Pre-unification scripts (deprecated, still work)
├── .github/workflows/ci.yml  # Lint (ruff) + tests (py3.9–3.12)
│
├── pyproject.toml            # Packaging + entry point + ruff/pytest config
├── README.md
├── CHANGELOG.md
├── LICENSE                   # MIT
├── ESTRUCTURA_CSV.md         # CSV schema for bulk worklog ops
├── .env.example              # Template for local credentials
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

CI runs `ruff check` and `pytest` on Python 3.9 through 3.12 for every push
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
