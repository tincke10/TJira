<p align="center">
  <img src="tjira-logo.svg" alt="TJira" width="300" />
</p>

<p align="center">
  <strong>The scissors for your Jira backlog.</strong><br>
  Cut through issues, worklogs and sprints — straight from the CLI.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white" alt="Python 3.9+" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
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

# 2. Configure — create a .env file (see section below)
#    with JIRA_DOMAIN / JIRA_EMAIL / JIRA_API_TOKEN

# 3. Go
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
│       ├── log.py            # tjira log
│       ├── issue.py          # tjira issue {get,create,update,transitions}
│       ├── list_cmd.py       # tjira list {issues,boards,sprints,...}
│       └── worklog.py        # tjira worklog {import,delete}
│
├── pyproject.toml            # Packaging + entry point
├── README.md
├── ESTRUCTURA_CSV.md         # CSV schema for bulk worklog ops
├── tjira-logo.svg            # Banner logo (with wordmark)
├── tjira-icon.svg            # Square app icon
│
└── (legacy scripts)          # log_hours.py, create_task.py, etc. — see below
```

<details>
<summary><b>Legacy scripts</b> (kept for backwards compatibility)</summary>

The original standalone scripts keep working. New usage should go through `tjira`.

```bash
# Worklogs
python log_hours.py PROJ-123 2h
python log_hours.py PROJ-123 "1h 30m" "2026-01-05 14:00"

# Issues
python create_task.py PROJ "Implement feature" --type Bug --desc "..."
python update_task.py PROJ-123 --status "In Progress" --assign me
python list_tasks.py --project PROJ --status "In Progress"

# Bulk
python import_worklogs.py worklogs.csv --dry-run
python delete_worklogs.py worklogs.csv
```

### `JiraClient` Python API

```python
from jira_client import JiraClient

client = JiraClient()
issue = client.get_issue("PROJ-123")
client.add_worklog(issue_key="PROJ-123", time_spent="2h",
                   started="2026-01-05T09:00:00.000+0100")
issues = client.search_issues("project = PROJ AND status = 'To Do'")
```

| Method                         | Description                       |
| ------------------------------ | --------------------------------- |
| `get_issue(key)`               | Get issue details                 |
| `create_issue(...)`            | Create new issue                  |
| `update_issue(key, fields)`    | Update issue fields               |
| `assign_issue(key, user_id)`   | Assign issue to user              |
| `transition_issue(key, id)`    | Change issue status               |
| `get_transitions(key)`         | Get available transitions         |
| `get_worklogs(key)`            | Get issue worklogs                |
| `add_worklog(...)`             | Add worklog entry                 |
| `delete_worklog(key, id)`      | Delete worklog                    |
| `search_issues(jql)`           | Search with JQL                   |
| `get_myself()`                 | Get current user info             |
| `search_users(query)`          | Search users                      |
| `get_projects()`               | List all projects                 |
| `get_project(key)`             | Get project details               |

</details>

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
