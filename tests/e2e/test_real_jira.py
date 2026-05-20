"""End-to-end tests against a REAL Jira Cloud instance.

Gated: skips cleanly when any of these env vars is missing:
    JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_TEST_ISSUE

`JIRA_TEST_ISSUE` MUST be a key (e.g. ``SANDBOX-1``) in a project where the
user controlled by the API token can freely create and delete worklogs. This
suite WILL create and delete worklogs on that issue — at a far-future slot
(2030-01-01) chosen to avoid colliding with real work — and cleans up in
``finally`` even when assertions fail.

Locally:
    JIRA_DOMAIN=mine.atlassian.net JIRA_EMAIL=... JIRA_API_TOKEN=... \\
    JIRA_TEST_ISSUE=SANDBOX-1 pytest tests/e2e/test_real_jira.py -v

In CI: configured as GitHub Actions secrets; see .github/workflows/ci.yml.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REQUIRED_ENV = ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_TEST_ISSUE")
REAL_JIRA = pytest.mark.skipif(
    not all(os.getenv(v) for v in REQUIRED_ENV),
    reason=f"real-Jira E2E disabled (set: {', '.join(REQUIRED_ENV)})",
)

# Additional gate for tests that mutate parent relationships (requires an existing Epic key).
REAL_JIRA_EPIC = pytest.mark.skipif(
    not os.getenv("JIRA_TEST_EPIC"),
    reason="JIRA_TEST_EPIC not set — skipping parent-mutation tests",
)

# Far-future slot, chosen so we never collide with real work.
SAFE_DATE = date(2030, 1, 1)
SAFE_START = "2030-01-01 09:00"   # 09:00-10:00 UTC after parsing
SAFE_START_LATE = "2030-01-01 09:30"  # overlaps with the first one


@pytest.fixture(scope="module")
def _real_client():
    """Direct JiraClient for cleanup work — bypasses subprocess overhead."""
    from tjira.client import JiraClient
    from tjira.profiles import Profile
    profile = Profile(
        name="ci",
        domain=os.environ["JIRA_DOMAIN"],
        email=os.environ["JIRA_EMAIL"],
        api_token=os.environ["JIRA_API_TOKEN"],
    )
    return JiraClient(profile=profile)


@pytest.fixture
def real_jira_env(tmp_path: Path) -> dict[str, str]:
    """Env that points the CLI at the real Jira via a temp TOML profile."""
    cfg_dir = tmp_path / "tjira"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text(
        f'current_profile = "ci"\n'
        f'\n'
        f'[profiles.ci]\n'
        f'domain = "{os.environ["JIRA_DOMAIN"]}"\n'
        f'email = "{os.environ["JIRA_EMAIL"]}"\n'
        f'api_token = "{os.environ["JIRA_API_TOKEN"]}"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({
        "XDG_CONFIG_HOME": str(tmp_path),
        "JIRA_TIMEZONE": "UTC",
        "NO_COLOR": "1",
        # The real Jira URL is built from the profile domain — make sure no
        # leftover override from another test points at localhost.
        "TJIRA_API_BASE_URL": "",
        "TJIRA_AGILE_BASE_URL": "",
    })
    env.pop("TJIRA_API_BASE_URL")
    env.pop("TJIRA_AGILE_BASE_URL")
    return env


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tjira", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _purge_safe_slot(client, issue: str) -> None:
    """Delete every worklog the current user has in the safe slot for this issue."""
    try:
        for wl in client.search_user_worklogs(SAFE_DATE, SAFE_DATE):
            if wl.get("_issue_key") == issue:
                try:
                    client.delete_worklog(issue, wl["id"])
                except Exception:
                    pass
    except Exception:
        pass


# ==================== READ-ONLY ====================

@REAL_JIRA
def test_real_doctor_passes(real_jira_env):
    """`tjira doctor` against the real instance must report all_passed."""
    result = _run(real_jira_env, "doctor", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["data"]["all_passed"] is True


@REAL_JIRA
def test_real_issue_get_returns_issue(real_jira_env):
    issue = os.environ["JIRA_TEST_ISSUE"]
    result = _run(real_jira_env, "issue", "get", issue, "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)["data"]
    assert data["key"] == issue


@REAL_JIRA
def test_real_list_boards_succeeds(real_jira_env):
    """May return zero boards; the only assertion is that the call returns 0."""
    result = _run(real_jira_env, "list", "boards", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert isinstance(envelope["data"], list)


# ==================== READ + WRITE: the full overlap cycle ====================

@REAL_JIRA
def test_real_log_overlap_cycle(real_jira_env, _real_client):
    """Create → trigger overlap (exit 3) → bypass with --force → cleanup."""
    issue = os.environ["JIRA_TEST_ISSUE"]
    _purge_safe_slot(_real_client, issue)  # defensive: previous run leftovers

    created_ids: list[str] = []
    try:
        # 1) Post a worklog at 09:00 (1h) — should succeed.
        r1 = _run(real_jira_env, "log", issue, "1h", SAFE_START, "--json")
        assert r1.returncode == 0, f"create #1 failed: {r1.stderr}"
        wl1 = json.loads(r1.stdout)["data"]
        created_ids.append(wl1["id"])

        # 2) Try a worklog at 09:30 (1h) — should hit overlap (exit 3).
        r2 = _run(real_jira_env, "log", issue, "1h", SAFE_START_LATE, "--json")
        assert r2.returncode == 3, (
            f"expected exit 3, got {r2.returncode}\n"
            f"stdout: {r2.stdout!r}\nstderr: {r2.stderr!r}"
        )
        envelope = next(
            json.loads(line) for line in reversed(r2.stderr.splitlines())
            if line.strip().startswith("{")
        )
        assert envelope["conflict"]["worklog_id"] == wl1["id"]
        # Existing 09:00 + 1h ends at 10:00 — that is the suggested next slot.
        assert "10:00" in envelope["suggested_start"]

        # 3) Same call with --force: should succeed (creates a true overlap).
        r3 = _run(
            real_jira_env, "log", issue, "1h", SAFE_START_LATE, "--force", "--json"
        )
        assert r3.returncode == 0, f"--force create failed: {r3.stderr}"
        wl3 = json.loads(r3.stdout)["data"]
        created_ids.append(wl3["id"])
    finally:
        # Always clean up — direct API calls so a broken CLI cannot block cleanup.
        for wl_id in created_ids:
            try:
                _real_client.delete_worklog(issue, wl_id)
            except Exception:
                pass
        # Defensive sweep: catch anything left over (other test interleaving, etc.).
        _purge_safe_slot(_real_client, issue)


# ==================== READ-ONLY: discovery commands ====================

@REAL_JIRA
def test_real_list_projects_succeeds(real_jira_env):
    """T6.1: list projects --json exits 0 and returns a JSON array with key+name on every item."""
    result = _run(real_jira_env, "list", "projects", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    projects = envelope["data"]
    assert isinstance(projects, list)
    for proj in projects:
        assert "key" in proj, f"project missing 'key': {proj}"
        assert "name" in proj, f"project missing 'name': {proj}"


@REAL_JIRA
def test_real_list_issue_types_succeeds(real_jira_env):
    """T6.2: list issue-types <project> --json exits 0 and returns a non-empty array.

    The project key is derived from the JIRA_TEST_ISSUE env var (e.g. SANDBOX-1 → SANDBOX).
    """
    test_issue = os.environ["JIRA_TEST_ISSUE"]
    project_key = test_issue.rsplit("-", 1)[0]

    result = _run(real_jira_env, "list", "issue-types", project_key, "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    issue_types = envelope["data"]
    assert isinstance(issue_types, list)
    assert len(issue_types) > 0, (
        f"Expected at least one issue type for project {project_key!r}, got empty list"
    )
    for it in issue_types:
        assert "id" in it
        assert "name" in it


@REAL_JIRA
def test_real_list_users_succeeds(real_jira_env):
    """T6.3: list users <fragment> --json exits 0 and returns a JSON array.

    Queries with the letter "a" — nearly guaranteed to return at least one user on any real tenant.
    """
    result = _run(real_jira_env, "list", "users", "a", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert isinstance(envelope["data"], list)


@REAL_JIRA
def test_real_list_fields_succeeds(real_jira_env):
    """T6.4: list fields <project> Task --json exits 0; stdout is a JSON array.

    The 'summary' field should be present and required on any next-gen project.
    Acceptable alternative: exits 2 when 'Task' does not exist in that project (some projects
    rename the type), which we also allow here by checking either condition.
    """
    test_issue = os.environ["JIRA_TEST_ISSUE"]
    project_key = test_issue.rsplit("-", 1)[0]

    result = _run(real_jira_env, "list", "fields", project_key, "Task", "--json")
    if result.returncode == 2:
        # 'Task' issue type may not exist in this project — acceptable per spec.
        err = json.loads(
            next(
                line for line in reversed(result.stderr.splitlines())
                if line.strip().startswith("{")
            )
        )
        assert "issue_type" in err or "error" in err
        return  # test passes — Jira confirmed the type doesn't exist
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    fields = envelope["data"]
    assert isinstance(fields, list)
    keys = {f["key"] for f in fields}
    assert "summary" in keys, f"Expected 'summary' field, got keys: {keys}"
    summary = next(f for f in fields if f["key"] == "summary")
    assert summary["required"] is True


# ==================== WRITE: parent mutation (gated on JIRA_TEST_EPIC) ====================

@REAL_JIRA
@REAL_JIRA_EPIC
def test_real_issue_create_with_parent(real_jira_env):
    """T6.5: Create an issue with --parent <EPIC> and assert the parent is set.

    Cleanup: deletes the created issue via direct API call when JIRA_ALLOW_CLEANUP=1.
    If JIRA_ALLOW_CLEANUP is not set, the test prints a stderr warning with the issue key
    to clean up manually.

    NOTE: The JiraClient does not expose a delete_issue() method (out of scope for this change).
    Cleanup is done via client._request("DELETE", ...) which is the underlying primitive.
    Users without JIRA_ALLOW_CLEANUP set must delete the test issue manually via the Jira UI
    or REST API: DELETE /rest/api/3/issue/{key}
    """
    import datetime

    from tjira.client import JiraClient
    from tjira.profiles import Profile

    test_issue = os.environ["JIRA_TEST_ISSUE"]
    project_key = test_issue.rsplit("-", 1)[0]
    epic_key = os.environ["JIRA_TEST_EPIC"]
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    summary = f"tjira-test-parent {timestamp}"

    created_key: str | None = None
    try:
        result = _run(
            real_jira_env,
            "issue", "create", project_key, summary,
            "--parent", epic_key,
            "--type", "Task",
            "--json",
        )
        assert result.returncode == 0, (
            f"issue create failed (returncode={result.returncode})\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        data = json.loads(result.stdout)["data"]
        created_key = data["key"]
        assert data["parent_key"] == epic_key, (
            f"Expected parent_key={epic_key!r}, got {data.get('parent_key')!r}"
        )
    finally:
        if created_key:
            if os.getenv("JIRA_ALLOW_CLEANUP") == "1":
                try:
                    profile = Profile(
                        name="ci",
                        domain=os.environ["JIRA_DOMAIN"],
                        email=os.environ["JIRA_EMAIL"],
                        api_token=os.environ["JIRA_API_TOKEN"],
                    )
                    client = JiraClient(profile=profile)
                    client._request("DELETE", f"issue/{created_key}", expected=(204,))
                except Exception as exc:
                    print(  # noqa: T201
                        f"WARNING: cleanup of {created_key} failed: {exc}", file=sys.stderr
                    )
            else:
                print(  # noqa: T201
                    f"WARNING: test issue {created_key} was not deleted. "
                    f"Set JIRA_ALLOW_CLEANUP=1 to enable auto-cleanup, "
                    f"or delete it manually via Jira UI / "
                    f"DELETE /rest/api/3/issue/{created_key}",
                    file=sys.stderr,
                )


@REAL_JIRA
@REAL_JIRA_EPIC
def test_real_issue_update_parent_set_and_clear(real_jira_env):
    """T6.6: Create issue without parent → set parent → assert set → clear → assert cleared.

    Cleanup: same policy as T6.5 (JIRA_ALLOW_CLEANUP=1 for auto-delete).

    NOTE: JiraClient.delete_issue() is not implemented (out of scope). Cleanup uses
    client._request("DELETE", ...) directly. Without JIRA_ALLOW_CLEANUP=1, the test issue
    will remain in Jira and must be cleaned up manually.
    """
    import datetime

    from tjira.client import JiraClient
    from tjira.profiles import Profile

    test_issue = os.environ["JIRA_TEST_ISSUE"]
    project_key = test_issue.rsplit("-", 1)[0]
    epic_key = os.environ["JIRA_TEST_EPIC"]
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    summary = f"tjira-test-reparent {timestamp}"

    created_key: str | None = None
    try:
        # Step 1: Create issue without parent.
        r_create = _run(
            real_jira_env,
            "issue", "create", project_key, summary,
            "--type", "Task",
            "--json",
        )
        assert r_create.returncode == 0, (
            f"issue create failed: {r_create.stderr}\n{r_create.stdout}"
        )
        created_key = json.loads(r_create.stdout)["data"]["key"]

        # Step 2: Set parent to epic.
        r_set = _run(
            real_jira_env,
            "issue", "update", created_key,
            "--parent", epic_key,
            "--json",
        )
        assert r_set.returncode == 0, (
            f"issue update --parent {epic_key} failed: {r_set.stderr}\n{r_set.stdout}"
        )
        set_data = json.loads(r_set.stdout)["data"]
        assert set_data["parent_key"] == epic_key, (
            f"Expected parent_key={epic_key!r} after set, got {set_data.get('parent_key')!r}"
        )

        # Step 3: Clear parent via --parent NONE.
        r_clear = _run(
            real_jira_env,
            "issue", "update", created_key,
            "--parent", "NONE",
            "--json",
        )
        assert r_clear.returncode == 0, (
            f"issue update --parent NONE failed: {r_clear.stderr}\n{r_clear.stdout}"
        )
        clear_data = json.loads(r_clear.stdout)["data"]
        assert clear_data["parent_key"] is None, (
            f"Expected parent_key=null after clear, got {clear_data.get('parent_key')!r}"
        )
    finally:
        if created_key:
            if os.getenv("JIRA_ALLOW_CLEANUP") == "1":
                try:
                    profile = Profile(
                        name="ci",
                        domain=os.environ["JIRA_DOMAIN"],
                        email=os.environ["JIRA_EMAIL"],
                        api_token=os.environ["JIRA_API_TOKEN"],
                    )
                    client = JiraClient(profile=profile)
                    client._request("DELETE", f"issue/{created_key}", expected=(204,))
                except Exception as exc:
                    print(  # noqa: T201
                        f"WARNING: cleanup of {created_key} failed: {exc}", file=sys.stderr
                    )
            else:
                print(  # noqa: T201
                    f"WARNING: test issue {created_key} was not deleted. "
                    f"Set JIRA_ALLOW_CLEANUP=1 to enable auto-cleanup, "
                    f"or delete it manually via Jira UI / "
                    f"DELETE /rest/api/3/issue/{created_key}",
                    file=sys.stderr,
                )
