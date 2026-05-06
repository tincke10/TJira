"""Tests for `JiraClient` — HTTP mocked with `responses`.

Validates that the client raises `APIError` with a structured payload on
failures and returns dicts/lists on success. No real network calls.
"""

from __future__ import annotations

import pytest
import responses

from tjira.errors import APIError


@pytest.fixture
def client(configured_profile):
    """Instantiate a ``JiraClient`` against the seeded test profile."""
    from tjira.client import JiraClient
    return JiraClient()


@responses.activate
def test_get_issue_returns_parsed_json(client):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1",
        json={"key": "PROJ-1", "fields": {"summary": "hi"}},
        status=200,
    )
    result = client.get_issue("PROJ-1")
    assert result["key"] == "PROJ-1"


@responses.activate
def test_get_issue_raises_api_error_on_404(client):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/MISSING",
        json={"errorMessages": ["Issue not found"]},
        status=404,
    )
    with pytest.raises(APIError) as exc_info:
        client.get_issue("MISSING")
    assert exc_info.value.payload["status"] == 404
    assert exc_info.value.payload["method"] == "GET"


@responses.activate
def test_create_issue_posts_expected_payload(client):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue",
        json={"key": "PROJ-42", "id": "100"},
        status=201,
    )
    result = client.create_issue("PROJ", "New task", issue_type="Bug", description="body")
    assert result["key"] == "PROJ-42"

    # Verify the body that was actually sent
    sent = responses.calls[0].request
    assert sent.method == "POST"
    body = sent.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert '"Bug"' in body
    assert '"New task"' in body


@responses.activate
def test_add_worklog_posts_and_returns_result(client):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "77", "timeSpent": "2h"},
        status=201,
    )
    result = client.add_worklog("PROJ-1", "2h", started="2026-04-20T09:00:00.000+0000")
    assert result == {"id": "77", "timeSpent": "2h"}


@responses.activate
def test_search_issues_uses_new_jql_endpoint(client):
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]},
        status=200,
    )
    result = client.search_issues("project = PROJ")
    assert [i["key"] for i in result] == ["PROJ-1", "PROJ-2"]


@responses.activate
def test_get_boards_hits_agile_endpoint(client):
    responses.get(
        "https://example.atlassian.net/rest/agile/1.0/board",
        json={"values": [{"id": 1, "name": "Board A", "type": "scrum"}]},
        status=200,
    )
    result = client.get_boards(project_key="PROJ", board_type="scrum")
    assert result[0]["name"] == "Board A"


@responses.activate
def test_transition_issue_sends_transition_id(client):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/transitions",
        status=204,
    )
    client.transition_issue("PROJ-1", "31")  # no return; no exception = OK
    assert len(responses.calls) == 1


@responses.activate
def test_network_error_becomes_api_error(client):
    # We do not register the URL, so `responses` raises ConnectionError.
    with pytest.raises(APIError) as exc_info:
        client.get_issue("PROJ-1")
    assert "Network failure" in exc_info.value.message


# ==================== search_user_worklogs ====================

from datetime import date


@responses.activate
def test_search_user_worklogs_filters_by_current_user_and_range(client):
    # /myself for accountId resolution
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123", "displayName": "Me", "emailAddress": "me@x.com"},
        status=200,
    )
    # JQL search returns the issues that have worklogs from current user in range
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]},
        status=200,
    )
    # PROJ-1 has one worklog from me, one from another user
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"worklogs": [
            {"id": "10", "author": {"accountId": "me-123"},
             "started": "2026-04-20T09:00:00.000+0000", "timeSpentSeconds": 3600,
             "timeSpent": "1h"},
            {"id": "11", "author": {"accountId": "other"},
             "started": "2026-04-20T10:00:00.000+0000", "timeSpentSeconds": 3600,
             "timeSpent": "1h"},
        ]},
        status=200,
    )
    # PROJ-2 has one worklog from me on a different day (out of range)
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-2/worklog",
        json={"worklogs": [
            {"id": "20", "author": {"accountId": "me-123"},
             "started": "2026-04-20T14:00:00.000+0000", "timeSpentSeconds": 1800,
             "timeSpent": "30m"},
            {"id": "21", "author": {"accountId": "me-123"},
             "started": "2026-04-25T09:00:00.000+0000", "timeSpentSeconds": 3600,
             "timeSpent": "1h"},
        ]},
        status=200,
    )

    result = client.search_user_worklogs(date(2026, 4, 20), date(2026, 4, 20))
    ids = sorted(wl["id"] for wl in result)
    assert ids == ["10", "20"]  # 11 is another user, 21 is out of range
    # Each returned worklog carries the issue key so callers can render conflicts.
    by_id = {wl["id"]: wl for wl in result}
    assert by_id["10"]["_issue_key"] == "PROJ-1"
    assert by_id["20"]["_issue_key"] == "PROJ-2"


@responses.activate
def test_search_user_worklogs_returns_empty_when_no_issues(client):
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    assert client.search_user_worklogs(date(2026, 4, 20), date(2026, 4, 20)) == []


@responses.activate
def test_search_user_worklogs_jql_uses_worklog_author_and_date_range(client):
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    client.search_user_worklogs(date(2026, 4, 20), date(2026, 4, 22))

    sent_body = responses.calls[1].request.body
    if isinstance(sent_body, bytes):
        sent_body = sent_body.decode("utf-8")
    import json as _json
    payload = _json.loads(sent_body)
    assert "worklogAuthor = currentUser()" in payload["jql"]
    assert 'worklogDate >= "2026-04-20"' in payload["jql"]
    assert 'worklogDate <= "2026-04-22"' in payload["jql"]


# ==================== base URL overrides ====================

@responses.activate
def test_base_url_env_var_overrides_default(monkeypatch, configured_profile):
    """TJIRA_API_BASE_URL replaces the default https://{domain}/rest/api/3."""
    monkeypatch.setenv("TJIRA_API_BASE_URL", "http://localhost:9999/rest/api/3")
    from tjira.client import JiraClient
    client_local = JiraClient()
    assert client_local.base_url == "http://localhost:9999/rest/api/3"

    responses.get(
        "http://localhost:9999/rest/api/3/issue/PROJ-1",
        json={"key": "PROJ-1"},
        status=200,
    )
    result = client_local.get_issue("PROJ-1")
    assert result["key"] == "PROJ-1"


@responses.activate
def test_agile_base_url_env_var_overrides_default(monkeypatch, configured_profile):
    monkeypatch.setenv("TJIRA_AGILE_BASE_URL", "http://localhost:9999/rest/agile/1.0")
    from tjira.client import JiraClient
    client_local = JiraClient()
    assert client_local.agile_url == "http://localhost:9999/rest/agile/1.0"


def test_base_url_default_unchanged_when_env_unset(configured_profile):
    from tjira.client import JiraClient
    client_local = JiraClient()
    assert client_local.base_url == "https://example.atlassian.net/rest/api/3"
    assert client_local.agile_url == "https://example.atlassian.net/rest/agile/1.0"


@responses.activate
def test_search_user_worklogs_caches_account_id(client):
    """Calling twice must hit /myself only once."""
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    client.search_user_worklogs(date(2026, 4, 20), date(2026, 4, 20))
    client.search_user_worklogs(date(2026, 4, 21), date(2026, 4, 21))

    myself_calls = [c for c in responses.calls if c.request.url.endswith("/myself")]
    assert len(myself_calls) == 1
