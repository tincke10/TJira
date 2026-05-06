"""Improved Jira client — wraps `requests` and raises `APIError` on failures.

Differences from `jira_client.py` (legacy, kept for backwards compatibility):
    - Raises `APIError` with a structured payload instead of returning `None`
      or `False`.
    - Configurable timeout via `JIRA_TIMEOUT` (default 30s).
    - Single entry point per method, instead of `(ok, result)` tuples.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from tjira.config import resolve_profile
from tjira.errors import APIError
from tjira.overlap import _parse_jira_started
from tjira.profiles import Profile

DEFAULT_TIMEOUT = float(os.getenv("JIRA_TIMEOUT", "30"))


class JiraClient:
    """Client for the Jira Cloud REST API."""

    def __init__(self, profile: Profile | None = None) -> None:
        prof = profile or resolve_profile()
        self.profile = prof
        # Env vars TJIRA_API_BASE_URL / TJIRA_AGILE_BASE_URL override the
        # default Atlassian Cloud URLs. Useful for tests (point at a localhost
        # mock server) and for Jira On-Premise / staging environments.
        self.base_url = (
            os.getenv("TJIRA_API_BASE_URL") or f"https://{prof.domain}/rest/api/3"
        )
        self.agile_url = (
            os.getenv("TJIRA_AGILE_BASE_URL") or f"https://{prof.domain}/rest/agile/1.0"
        )
        self.browse_url = f"https://{prof.domain}/browse"
        self.auth = HTTPBasicAuth(prof.email, prof.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._account_id: str | None = None

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

    def get_account_id(self) -> str:
        """Return the current user's accountId, cached after the first call."""
        if self._account_id is None:
            self._account_id = self.get_myself().get("accountId") or ""
        return self._account_id

    def search_user_worklogs(self, date_from: date, date_to: date) -> list[dict]:
        """Return all worklogs authored by the current user in ``[date_from, date_to]``.

        Each returned worklog has an extra ``_issue_key`` field with the issue
        it belongs to, so callers can render conflicts without an extra lookup.
        """
        my_account_id = self.get_account_id()
        jql = (
            f"worklogAuthor = currentUser() "
            f'AND worklogDate >= "{date_from.isoformat()}" '
            f'AND worklogDate <= "{date_to.isoformat()}"'
        )
        issues = self.search_issues(jql, max_results=100)

        # Window in UTC for filtering started timestamps. We accept anything
        # whose start lies within the [date_from 00:00, date_to+1d 00:00) window
        # in UTC — wide enough that timezone differences won't drop legitimate
        # entries. Per-day precision is the contract.
        win_start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        win_end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)

        out: list[dict] = []
        for issue in issues:
            key = issue.get("key")
            if not key:
                continue
            for wl in self.get_worklogs(key):
                author = (wl.get("author") or {}).get("accountId")
                if author != my_account_id:
                    continue
                started_raw = wl.get("started")
                if not started_raw:
                    continue
                try:
                    started_dt = _parse_jira_started(started_raw)
                except ValueError:
                    continue
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
                started_utc = started_dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
                if not (win_start <= started_utc <= win_end):
                    continue
                wl["_issue_key"] = key
                out.append(wl)
        return out

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
