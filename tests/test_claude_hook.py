"""Tests for .claude/hooks/tjira-timer-hook.sh

The hook script is exercised as a real subprocess. A tiny shim `tjira` is
placed on PATH ahead of any real binary. The shim records its args to a log
file so assertions can inspect which subcommands were invoked (or not).

All tests are skipped on Windows — the hook is a POSIX-only sh script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only hook script")

# Absolute path to the hook script under test.
_HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "tjira-timer-hook.sh"


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Init a git repo with branch feat/PROJ-1-foo."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init", "-q"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "checkout", "-q", "-b", "feat/PROJ-1-foo"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def tjira_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Place a shim `tjira` binary on PATH that:
    - Records each invocation (space-joined argv) into a log file.
    - Responds to `timer status --json` based on env var TJIRA_STUB_ACTIVE_KEY:
        * If set → returns active-timer JSON for that key.
        * If unset → returns no-active-timer JSON.
    - Exits 0 for all invocations.

    Returns the Path to the log file (may be empty if no invocations occurred).
    """
    bin_dir = tmp_path / "stub_bin"
    bin_dir.mkdir()
    log_file = tmp_path / "tjira_invocations.log"

    stub = bin_dir / "tjira"
    stub.write_text(
        f"""#!/bin/sh
echo "$@" >> "{log_file}"
case "$*" in
  "timer status --json")
    if [ -n "$TJIRA_STUB_ACTIVE_KEY" ]; then
      printf '{{"ok":true,"data":{{"issue_key":"%s","started_at":"2026-05-20T09:00:00.000+0000","elapsed":"1m"}}}}' "$TJIRA_STUB_ACTIVE_KEY"
    else
      printf '{{"ok":true,"data":null}}'
    fi
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return log_file


def _run_hook(
    event: str,
    cwd_json: str | None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook script with the given event and optional stdin JSON."""
    base_env = os.environ.copy()
    if env:
        base_env.update(env)
    stdin_bytes = (cwd_json or "").encode("utf-8")
    return subprocess.run(
        [str(_HOOK), event],
        input=stdin_bytes,
        capture_output=True,
        env=base_env,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# T4.1 — degenerate input: no event arg, empty stdin → exit 0
# ---------------------------------------------------------------------------

def test_hook_empty_event_exits_0(tmp_path: Path):
    """Hook invoked with no arguments must exit 0 without crashing."""
    result = subprocess.run(
        [str(_HOOK)],
        input=b"",
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T4.2 — SessionStart + matching branch + no active timer → timer start invoked
# ---------------------------------------------------------------------------

def test_hook_session_start_matching_branch_no_active_timer_starts(
    git_repo: Path,
    tjira_stub,
):
    """SessionStart on feat/PROJ-1-foo with no active timer → tjira timer start PROJ-1."""
    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("SessionStart", stdin_json)

    assert result.returncode == 0
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer start PROJ-1" in log_text


# ---------------------------------------------------------------------------
# T4.3 — SessionStart + matching branch + active timer for SAME key → no-op
# ---------------------------------------------------------------------------

def test_hook_session_start_same_key_active_noop(
    git_repo: Path,
    tjira_stub,
    monkeypatch: pytest.MonkeyPatch,
):
    """SessionStart + active timer already running for PROJ-1 → no start invoked."""
    monkeypatch.setenv("TJIRA_STUB_ACTIVE_KEY", "PROJ-1")
    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("SessionStart", stdin_json)

    assert result.returncode == 0
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer start" not in log_text


# ---------------------------------------------------------------------------
# T4.4 — SessionStart + matching branch + active timer for DIFFERENT key → no-op
# ---------------------------------------------------------------------------

def test_hook_session_start_different_key_active_noop(
    git_repo: Path,
    tjira_stub,
    monkeypatch: pytest.MonkeyPatch,
):
    """SessionStart + active timer for PROJ-456 (not PROJ-1) → no replace."""
    monkeypatch.setenv("TJIRA_STUB_ACTIVE_KEY", "PROJ-456")
    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("SessionStart", stdin_json)

    assert result.returncode == 0
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer start" not in log_text


# ---------------------------------------------------------------------------
# T4.5 — SessionStart + branch without issue key → no-op
# ---------------------------------------------------------------------------

def test_hook_session_start_non_matching_branch_noop(tmp_path: Path, tjira_stub):
    """SessionStart on branch 'main' (no PROJ-N pattern) → no tjira call."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init", "-q"], cwd=tmp_path, check=True
    )
    # stays on main branch (default)

    stdin_json = json.dumps({"cwd": str(tmp_path)})
    result = _run_hook("SessionStart", stdin_json)

    assert result.returncode == 0
    # No tjira invocations at all (log file should not exist or be empty)
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer start" not in log_text


# ---------------------------------------------------------------------------
# T4.6 — SessionStart + cwd is not a git repo → exit 0, no tjira call
# ---------------------------------------------------------------------------

def test_hook_session_start_not_git_repo_exits_0(tmp_path: Path, tjira_stub):
    """If cwd is not a git repo, hook must exit 0 silently without invoking tjira."""
    # tmp_path has no .git — it's definitely not a git repo
    stdin_json = json.dumps({"cwd": str(tmp_path)})
    result = _run_hook("SessionStart", stdin_json)

    assert result.returncode == 0
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer start" not in log_text


# ---------------------------------------------------------------------------
# T4.7 — Stop + active timer → timer stop invoked
# ---------------------------------------------------------------------------

def test_hook_stop_active_timer_invokes_stop(
    git_repo: Path,
    tjira_stub,
    monkeypatch: pytest.MonkeyPatch,
):
    """Stop event with an active timer → tjira timer stop is invoked."""
    monkeypatch.setenv("TJIRA_STUB_ACTIVE_KEY", "PROJ-1")
    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("Stop", stdin_json)

    assert result.returncode == 0
    log_text = tjira_stub.read_text(encoding="utf-8") if tjira_stub.exists() else ""
    assert "timer stop" in log_text


# ---------------------------------------------------------------------------
# T4.8 — Stop + no active timer → hook exits 0 (tolerates stop exit 1)
# ---------------------------------------------------------------------------

def test_hook_stop_no_active_timer_exits_0(
    git_repo: Path,
    tjira_stub,
):
    """Stop with no active timer — hook exits 0 regardless (|| true)."""
    # No TJIRA_STUB_ACTIVE_KEY → stub returns data:null for status
    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("Stop", stdin_json)

    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T4.9 — tjira absent from PATH → exit 0 silently
# ---------------------------------------------------------------------------

def test_hook_tjira_absent_from_path_exits_0(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    """If tjira is not on PATH the hook must still exit 0 (never blocks)."""
    # Point PATH at an empty dir so `command -v tjira` fails.
    empty_bin = git_repo / "empty_bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    stdin_json = json.dumps({"cwd": str(git_repo)})
    result = _run_hook("SessionStart", stdin_json)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T4.10 — hook always exits 0 regardless of what commands return
# ---------------------------------------------------------------------------

def test_hook_always_exits_0_on_failing_tjira(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Even when tjira exits non-zero, the hook must exit 0."""
    # Create a stub that always exits 1
    bin_dir = tmp_path / "bad_bin"
    bin_dir.mkdir()
    bad_stub = bin_dir / "tjira"
    bad_stub.write_text("#!/bin/sh\nexit 1\n")
    bad_stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    stdin_json = json.dumps({"cwd": str(git_repo)})

    # SessionStart — should not propagate tjira's exit 1
    result = _run_hook("SessionStart", stdin_json)
    assert result.returncode == 0

    # Stop — same
    result = _run_hook("Stop", stdin_json)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T4.11+T4.12 are the IMPL tasks (hook script + settings.json) — verified below
# via structural assertions rather than new tests.
# ---------------------------------------------------------------------------

def test_hook_script_has_execute_bit():
    """The hook script must have the execute bit set (0o755 or similar)."""
    assert _HOOK.exists(), f"Hook script not found at {_HOOK}"
    mode = _HOOK.stat().st_mode
    assert mode & 0o100, f"Execute bit not set on {_HOOK} (mode={oct(mode)})"


def test_settings_json_declares_both_hooks():
    """
    .claude/settings.json must declare both SessionStart and Stop hooks
    pointing at the hook script.
    """
    settings_path = _HOOK.parent.parent / "settings.json"
    assert settings_path.exists(), f".claude/settings.json not found at {settings_path}"

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})

    assert "SessionStart" in hooks, "Missing 'SessionStart' in hooks"
    assert "Stop" in hooks, "Missing 'Stop' in hooks"

    # At least one hook entry per event must reference the script
    def _any_command_references(entries: list, script_name: str) -> bool:
        for entry in entries:
            for h in entry.get("hooks", []):
                if script_name in h.get("command", ""):
                    return True
        return False

    assert _any_command_references(
        hooks["SessionStart"], "tjira-timer-hook.sh"
    ), "SessionStart hook does not reference tjira-timer-hook.sh"
    assert _any_command_references(
        hooks["Stop"], "tjira-timer-hook.sh"
    ), "Stop hook does not reference tjira-timer-hook.sh"
