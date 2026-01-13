# Jira Worklog Manager

CLI tool to manage Jira tasks and worklogs via REST API. Automate time tracking, task creation, and issue management from the command line.

## Features

- **Log Hours**: Register worklogs with specific dates and times
- **Create Tasks**: Create issues (Task, Bug, Story, Epic)
- **Update Tasks**: Modify summary, status, and assignee
- **List Tasks**: Search and filter issues using JQL
- **Bulk Import**: Import worklogs from CSV files
- **Bulk Delete**: Remove worklogs from multiple issues

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/JiraGestionREST.git
cd JiraGestionREST

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Get your Jira API token from: https://id.atlassian.com/manage-profile/security/api-tokens

2. Create a `.env` file in the project root:

```env
JIRA_DOMAIN=your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_api_token_here
```

## Usage

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
├── .gitignore
├── README.md
├── requirements.txt
├── config.py             # Configuration loader
├── jira_client.py        # Reusable Jira API client
├── log_hours.py          # Log worklogs
├── create_task.py        # Create issues
├── update_task.py        # Update issues
├── list_tasks.py         # Search issues
├── import_worklogs.py    # Bulk import from CSV
└── delete_worklogs.py    # Bulk delete worklogs
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
