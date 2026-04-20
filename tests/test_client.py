"""Tests para `JiraClient` — HTTP mockeado con `responses`.

Valida que el cliente lanza APIError con payload estructurado en fallas y
devuelve dicts/listas en éxitos. No hace red real.
"""

from __future__ import annotations

import pytest
import responses

from tjira.errors import APIError


@pytest.fixture
def client(configured_env):
    """Instancia un JiraClient con env mockeado."""
    # Import diferido: configured_env setea env vars antes de que `JiraClient`
    # lea `JIRA_DOMAIN` al construirse.
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

    # Verificamos el body enviado
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
    # No registramos la URL → responses levanta ConnectionError
    with pytest.raises(APIError) as exc_info:
        client.get_issue("PROJ-1")
    assert "Fallo de red" in exc_info.value.message
