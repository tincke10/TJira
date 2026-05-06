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
