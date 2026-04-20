"""Improved Jira client — wraps `requests` and raises `APIError` on failures.

Differences from `jira_client.py` (legacy, kept for backwards compatibility):
    - Raises `APIError` with a structured payload instead of returning `None`
      or `False`.
    - Configurable timeout via `JIRA_TIMEOUT` (default 30s).
    - Single entry point per method, instead of `(ok, result)` tuples.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from tjira.config import (
    JIRA_API_TOKEN,
    JIRA_DOMAIN,
    JIRA_EMAIL,
    validate_config,
)
from tjira.errors import APIError

DEFAULT_TIMEOUT = float(os.getenv("JIRA_TIMEOUT", "30"))


class JiraClient:
    """Client for the Jira Cloud REST API."""

    def __init__(self) -> None:
        validate_config()
        self.base_url = f"https://{JIRA_DOMAIN}/rest/api/3"
        self.agile_url = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
        self.browse_url = f"https://{JIRA_DOMAIN}/browse"
        self.auth = HTTPBasicAuth(JIRA_EMAIL or "", JIRA_API_TOKEN or "")
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ---------- internals ----------

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        base: str | None = None,
        data: dict | None = None,
        params: dict | None = None,
        expected: tuple[int, ...] = (200, 201, 204),
    ) -> requests.Response:
        url = f"{base or self.base_url}/{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                auth=self.auth,
                json=data,
                params=params,
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise APIError(
                f"Network failure calling Jira: {exc}",
                payload={"endpoint": endpoint, "method": method},
            ) from exc

        if response.status_code not in expected:
            raise APIError(
                f"Jira returned {response.status_code} on {method} {endpoint}",
                payload={
                    "endpoint": endpoint,
                    "method": method,
                    "status": response.status_code,
                    "body": _safe_body(response),
                },
            )
        return response

    # ==================== ISSUES ====================

    def get_issue(self, issue_key: str) -> dict:
        return self._request("GET", f"issue/{issue_key}", expected=(200,)).json()

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str | None = None,
        assignee_id: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }
        if description:
            payload["fields"]["description"] = _plain_to_adf(description)
        if assignee_id:
            payload["fields"]["assignee"] = {"id": assignee_id}
        return self._request("POST", "issue", data=payload, expected=(201,)).json()

    def update_issue(self, issue_key: str, fields: dict) -> None:
        self._request("PUT", f"issue/{issue_key}", data={"fields": fields}, expected=(204,))

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._request(
            "POST",
            f"issue/{issue_key}/transitions",
            data={"transition": {"id": transition_id}},
            expected=(204,),
        )

    def get_transitions(self, issue_key: str) -> list[dict]:
        response = self._request("GET", f"issue/{issue_key}/transitions", expected=(200,))
        return response.json().get("transitions", [])

    def assign_issue(self, issue_key: str, assignee_id: str) -> None:
        self._request(
            "PUT",
            f"issue/{issue_key}/assignee",
            data={"accountId": assignee_id},
            expected=(204,),
        )

    # ==================== WORKLOGS ====================

    def get_worklogs(self, issue_key: str) -> list[dict]:
        response = self._request("GET", f"issue/{issue_key}/worklog", expected=(200,))
        return response.json().get("worklogs", [])

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        started: str | None = None,
        comment: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"timeSpent": time_spent}
        if started:
            payload["started"] = started
        if comment:
            payload["comment"] = _plain_to_adf(comment)
        return self._request(
            "POST", f"issue/{issue_key}/worklog", data=payload, expected=(201,)
        ).json()

    def delete_worklog(self, issue_key: str, worklog_id: str) -> None:
        self._request("DELETE", f"issue/{issue_key}/worklog/{worklog_id}", expected=(204,))

    # ==================== SEARCH ====================

    def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
        # Jira Cloud deprecated /rest/api/3/search (410 Gone). Current endpoint:
        # POST /rest/api/3/search/jql — paginated via nextPageToken, no `total`.
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "issuetype", "priority"],
        }
        response = self._request("POST", "search/jql", data=payload, expected=(200,))
        return response.json().get("issues", [])

    # ==================== USERS ====================

    def get_myself(self) -> dict:
        return self._request("GET", "myself", expected=(200,)).json()

    def search_users(self, query: str) -> list[dict]:
        response = self._request("GET", "user/search", params={"query": query}, expected=(200,))
        return response.json()

    # ==================== PROJECTS ====================

    def get_projects(self) -> list[dict]:
        return self._request("GET", "project", expected=(200,)).json()

    def get_project(self, project_key: str) -> dict:
        return self._request("GET", f"project/{project_key}", expected=(200,)).json()

    # ==================== BOARDS / SPRINTS ====================

    def get_boards(
        self, project_key: str | None = None, board_type: str | None = None
    ) -> list[dict]:
        params = {}
        if project_key:
            params["projectKeyOrId"] = project_key
        if board_type:
            params["type"] = board_type
        response = self._request(
            "GET", "board", base=self.agile_url, params=params, expected=(200,)
        )
        return response.json().get("values", [])

    def get_board_issues(self, board_id: int, max_results: int = 50) -> list[dict]:
        response = self._request(
            "GET",
            f"board/{board_id}/issue",
            base=self.agile_url,
            params={"maxResults": max_results},
            expected=(200,),
        )
        return response.json().get("issues", [])

    def get_board_sprints(self, board_id: int, state: str = "active") -> list[dict]:
        response = self._request(
            "GET",
            f"board/{board_id}/sprint",
            base=self.agile_url,
            params={"state": state},
            expected=(200,),
        )
        return response.json().get("values", [])

    def get_sprint_issues(self, sprint_id: int, max_results: int = 50) -> list[dict]:
        response = self._request(
            "GET",
            f"sprint/{sprint_id}/issue",
            base=self.agile_url,
            params={"maxResults": max_results},
            expected=(200,),
        )
        return response.json().get("issues", [])

    # ==================== FILTERS ====================

    def get_filters(self, filter_name: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"expand": "jql"}
        if filter_name:
            params["filterName"] = filter_name
        response = self._request("GET", "filter/search", params=params, expected=(200,))
        return response.json().get("values", [])

    def get_filter(self, filter_id: int) -> dict:
        return self._request("GET", f"filter/{filter_id}", expected=(200,)).json()

    def get_filter_issues(self, filter_id: int, max_results: int = 50) -> list[dict]:
        filter_data = self.get_filter(filter_id)
        jql = filter_data.get("jql")
        if not jql:
            return []
        return self.search_issues(jql, max_results)

    # ==================== DASHBOARDS ====================

    def get_dashboards(self) -> list[dict]:
        response = self._request("GET", "dashboard", expected=(200,))
        return response.json().get("dashboards", [])

    # ==================== ATTACHMENTS ====================

    def add_attachment(self, issue_key: str, file_path: str) -> list[dict]:
        if not os.path.exists(file_path):
            raise APIError(
                f"File not found: {file_path}",
                payload={"file": file_path},
            )
        url = f"{self.base_url}/issue/{issue_key}/attachments"
        headers = {"Accept": "application/json", "X-Atlassian-Token": "no-check"}
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                response = requests.post(
                    url, headers=headers, auth=self.auth, files=files, timeout=DEFAULT_TIMEOUT
                )
        except requests.RequestException as exc:
            raise APIError(f"Network failure uploading attachment: {exc}") from exc
        if response.status_code != 200:
            raise APIError(
                f"Jira returned {response.status_code} while attaching file",
                payload={"status": response.status_code, "body": _safe_body(response)},
            )
        return response.json()

    # ==================== DESCRIPTION / COMMENTS ====================

    def update_description(self, issue_key: str, description: str) -> None:
        self.update_issue(issue_key, {"description": _plain_to_adf(description)})

    def add_comment(self, issue_key: str, body: str) -> dict:
        payload = {"body": _plain_to_adf(body)}
        return self._request(
            "POST", f"issue/{issue_key}/comment", data=payload, expected=(201,)
        ).json()


# ==================== helpers ====================

def _plain_to_adf(text: str) -> dict:
    """Wrap plain text in the minimal ADF document format Jira accepts."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _safe_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]
