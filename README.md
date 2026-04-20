# Jira Worklog Manager

CLI tool to manage Jira tasks and worklogs via REST API. Automate time tracking, task creation, and issue management from the command line.

Ships as **`tjira-cli`** — a unified CLI with `--json` output on every command, designed to be consumed by humans, scripts, or AI agents (Claude, GPT, CI jobs).

## Features

- **Unified CLI (`tjira-cli`)** — one entry point, subcommands (`log`, `issue`, `list`, `worklog`)
- **AI-friendly output** — `--json` flag on every command with stable schema; logs on stderr, data on stdout
- **Standard exit codes** — `0` OK, `1` user error, `2` API error
- **Timezone-aware** — configurable via `JIRA_TIMEZONE` (defaults to system local)
- **Legacy scripts preserved** — the original `log_hours.py`, `create_task.py`, etc. keep working

## Installation

### Option A — `pipx` (recommended)

```bash
pipx install .
tjira-cli --help
```

### Option B — editable install in a venv

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
pip install -e .
```

### Option C — run without installing

```bash
pip install --user typer requests python-dotenv
python3 -m tjira_cli --help
```

## Configuration

1. Get your Jira API token from: https://id.atlassian.com/manage-profile/security/api-tokens

2. Create a `.env` file in the project root:

```env
JIRA_DOMAIN=your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_api_token_here

# Optional: override the system timezone used for worklogs
JIRA_TIMEZONE=America/Argentina/Buenos_Aires

# Optional: HTTP timeout in seconds (default 30)
JIRA_TIMEOUT=30
```

## `tjira-cli` — Unified CLI

All commands accept `--json` for machine-readable output. Without it, output is human-friendly tables.

**Output contract**
- `stdout` → data (human table or JSON envelope `{"ok": true, "data": ...}`)
- `stderr` → progress logs (or `{"ok": false, "error": ...}` on failure)
- Exit codes: `0` OK · `1` user error · `2` Jira/API error

### Worklogs

```bash
# Single worklog
tjira-cli log PROJ-123 2h
tjira-cli log PROJ-123 "1h 30m" "2026-04-20"
tjira-cli log PROJ-123 45m "2026-04-20 09:00" --comment "Bug fix" --json

# Bulk import from CSV (see ESTRUCTURA_CSV.md)
tjira-cli worklog import worklogs.csv --dry-run
tjira-cli worklog import worklogs.csv --json

# Bulk delete all worklogs of issues in CSV
tjira-cli worklog delete worklogs.csv --dry-run
```

### Issues

```bash
# Get detail
tjira-cli issue get PROJ-123
tjira-cli issue get PROJ-123 --json

# Create
tjira-cli issue create PROJ "Implement feature X"
tjira-cli issue create PROJ "Fix login bug" --type Bug --desc "Steps to reproduce..."

# Update
tjira-cli issue update PROJ-123 --summary "New title"
tjira-cli issue update PROJ-123 --status "In Progress"
tjira-cli issue update PROJ-123 --assign me
tjira-cli issue update PROJ-123 --comment "Done" --attach screenshot.png

# Available transitions
tjira-cli issue transitions PROJ-123 --json
```

### Lists / Search

```bash
# Issues
tjira-cli list issues                                    # my open issues
tjira-cli list issues --project PROJ --json
tjira-cli list issues --jql "project = PROJ AND created >= -7d" --limit 50

# Boards / Sprints
tjira-cli list boards --project PROJ
tjira-cli list sprints 365
tjira-cli list sprint-issues 1234 --json
tjira-cli list board-issues 365 --json

# Saved filters & dashboards
tjira-cli list filters
tjira-cli list filter-issues 10042 --json
tjira-cli list dashboards
```

### AI integration example

With `--json` plus standard exit codes, any agent can safely invoke the CLI:

```bash
# Claude Code / any LLM tool call
result=$(tjira-cli list issues --project PROJ --json)
if [ $? -eq 0 ]; then
  echo "$result" | jq '.data.issues[] | {key, status}'
fi
```

---

## Legacy scripts (preserved for backwards compatibility)

> The scripts below are kept working for backwards compatibility. New usage should go through `tjira-cli`.

### Log Hours

```bash
# Log 2 hours now
python log_hours.py PROJ-123 2h

# Log with specific date
python log_hours.py PROJ-123 2h "2026-01-05"

# Log with specific date and time
python log_hours.py PROJ-123 "1h 30m" "2026-01-05 14:00"
```

### Create Tasks

```bash
# Create a task
python create_task.py PROJ "Implement new feature"

# Create a bug
python create_task.py PROJ "Fix login error" --type Bug

# Create with description
python create_task.py PROJ "Add caching" --desc "Implement Redis caching for API responses"
```

### Update Tasks

```bash
# View task details
python update_task.py PROJ-123

# Update title
python update_task.py PROJ-123 --summary "New title"

# Change status
python update_task.py PROJ-123 --status "In Progress"

# Assign to yourself
python update_task.py PROJ-123 --assign me

# View available transitions
python update_task.py PROJ-123 --transitions
```

### List Tasks

```bash
# List your pending tasks
python list_tasks.py

# Filter by project
python list_tasks.py --project PROJ

# Filter by status
python list_tasks.py --status "In Progress"

# Custom JQL query
python list_tasks.py --jql "project = PROJ AND created >= -7d"

# Limit results
python list_tasks.py --limit 50
```

### Bulk Import Worklogs

Create a CSV file with the following format:

```csv
Jira Key,Task ID,Summary,Date,Started,Time Spent,Author
PROJ-123,T-001,Task description,Monday 05/01,2026-01-05T09:00:00.000+0100,2h,email@company.com
PROJ-124,T-002,Another task,Monday 05/01,2026-01-05T11:00:00.000+0100,3h,email@company.com
```

Then import:

```bash
# Preview what will be imported
python import_worklogs.py worklogs.csv --dry-run

# Import worklogs
python import_worklogs.py worklogs.csv
```

### Delete Worklogs

```bash
# Preview what will be deleted
python delete_worklogs.py worklogs.csv --dry-run

# Delete all worklogs from issues in CSV
python delete_worklogs.py worklogs.csv
```

## Project Structure

```
JiraGestionREST/
├── .env                  # Credentials (not in repo)
├── pyproject.toml        # Packaging + entry point (tjira-cli)
├── README.md
├── requirements.txt      # Legacy deps (pyproject is the source of truth)
│
├── tjira_cli/            # Unified CLI package (NEW)
│   ├── cli.py            # Typer app + entry point
│   ├── client.py         # Jira REST client (raises APIError on failures)
│   ├── config.py         # Credentials + env validation
│   ├── errors.py         # Exit codes + typed exceptions
│   ├── formatters.py     # Human vs JSON output normalizers
│   ├── tz.py             # Timezone-aware datetime handling
│   └── commands/
│       ├── log.py        # tjira-cli log
│       ├── issue.py      # tjira-cli issue {get,create,update,transitions}
│       ├── list_cmd.py   # tjira-cli list {issues,boards,sprints,...}
│       └── worklog.py    # tjira-cli worklog {import,delete}
│
├── config.py             # Legacy config loader (kept for old scripts)
├── jira_client.py        # Legacy client (kept for old scripts)
├── log_hours.py          # Legacy: log worklogs
├── create_task.py        # Legacy: create issues
├── update_task.py        # Legacy: update issues
├── list_tasks.py         # Legacy: search issues
├── import_worklogs.py    # Legacy: bulk import from CSV
└── delete_worklogs.py    # Legacy: bulk delete worklogs
```

## JiraClient API

The `JiraClient` class can be imported and used in your own scripts:

```python
from jira_client import JiraClient

client = JiraClient()

# Get issue details
issue = client.get_issue("PROJ-123")

# Create issue
success, result = client.create_issue(
    project_key="PROJ",
    summary="New task",
    issue_type="Task",
    description="Task description"
)

# Add worklog
success, result = client.add_worklog(
    issue_key="PROJ-123",
    time_spent="2h",
    started="2026-01-05T09:00:00.000+0100"
)

# Search with JQL
issues = client.search_issues("project = PROJ AND status = 'To Do'")

# Get available transitions
transitions = client.get_transitions("PROJ-123")

# Change status
client.transition_issue("PROJ-123", transition_id="31")
```

## Available JiraClient Methods

| Method | Description |
|--------|-------------|
| `get_issue(key)` | Get issue details |
| `create_issue(...)` | Create new issue |
| `update_issue(key, fields)` | Update issue fields |
| `assign_issue(key, user_id)` | Assign issue to user |
| `transition_issue(key, id)` | Change issue status |
| `get_transitions(key)` | Get available transitions |
| `get_worklogs(key)` | Get issue worklogs |
| `add_worklog(...)` | Add worklog entry |
| `delete_worklog(key, id)` | Delete worklog |
| `search_issues(jql)` | Search with JQL |
| `get_myself()` | Get current user info |
| `search_users(query)` | Search users |
| `get_projects()` | List all projects |
| `get_project(key)` | Get project details |

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
