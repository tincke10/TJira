# Legacy scripts

> **These scripts are deprecated.** They are preserved so existing automation, cron jobs and shell aliases keep working. New code should use the unified [`tjira`](../README.md) CLI.

## Why they're still here

They predate the `tjira` package. Users and agents already rely on their paths
(e.g. `python log_hours.py PROJ-123 2h` in CI pipelines), so deleting them would
be a breaking change for the community.

## Mapping to the new CLI

| Legacy script                     | `tjira` equivalent                     |
| --------------------------------- | -------------------------------------- |
| `log_hours.py`                    | `tjira log`                            |
| `create_task.py`                  | `tjira issue create`                   |
| `update_task.py`                  | `tjira issue update`                   |
| `list_tasks.py`                   | `tjira list issues`                    |
| `import_worklogs.py`              | `tjira worklog import`                 |
| `delete_worklogs.py`              | `tjira worklog delete`                 |
| `jira_client.JiraClient` (Python) | `from tjira.client import JiraClient`  |

## Running a legacy script

From the project root:

```bash
python legacy/log_hours.py PROJ-123 2h
python legacy/create_task.py PROJ "New task" --type Bug
python legacy/list_tasks.py --project PROJ
python legacy/import_worklogs.py worklogs.csv --dry-run
```

Or from inside this directory:

```bash
cd legacy
python log_hours.py PROJ-123 2h
```

## `JiraClient` Python API (legacy)

```python
from legacy.jira_client import JiraClient

client = JiraClient()
issue = client.get_issue("PROJ-123")
client.add_worklog(issue_key="PROJ-123", time_spent="2h",
                   started="2026-01-05T09:00:00.000+0100")
issues = client.search_issues("project = PROJ AND status = 'To Do'")
```

For new code, prefer:

```python
from tjira.client import JiraClient   # raises APIError instead of returning None
```

## Sunset policy

The legacy scripts will remain in this directory for **at least** one major
release after feature parity is reached in `tjira`. A deprecation warning will
be printed when they are executed (planned — not yet implemented).
