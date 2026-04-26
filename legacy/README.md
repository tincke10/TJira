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

The legacy scripts read credentials from the process environment
(`JIRA_DOMAIN` / `JIRA_EMAIL` / `JIRA_API_TOKEN`). Since `python-dotenv` is no
longer a project dependency, you must source your `.env` file manually before
running them:

```bash
set -a && . ./.env && set +a            # one-time per shell
python legacy/log_hours.py PROJ-123 2h
```

Or export the variables some other way (your shell rc, a secrets manager, CI):

```bash
export JIRA_DOMAIN=your-company.atlassian.net
export JIRA_EMAIL=you@your-company.com
export JIRA_API_TOKEN=ATATT...
python legacy/log_hours.py PROJ-123 2h
```

From inside this directory it works the same:

```bash
cd legacy
set -a && . ../.env && set +a
python log_hours.py PROJ-123 2h
```

> **Tip:** If you would rather not juggle env vars at all, the new `tjira` CLI
> stores credentials in `~/.config/tjira/config.toml`. See the project README
> for `tjira profile add --from-env` to migrate.

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
