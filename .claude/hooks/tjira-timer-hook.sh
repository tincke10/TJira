#!/bin/sh
# tjira-timer-hook.sh — Claude Code SessionStart/Stop dispatcher.
# Automatically starts a worklog timer when opening Claude Code on a
# Jira-tagged branch (feat/PROJ-123-...) and stops it on session end.
#
# Always exits 0 — this hook must never block the Claude session.

EVENT="${1:-}"
[ -z "$EVENT" ] && exit 0

# Bail silently if tjira is not installed / not on PATH.
command -v tjira >/dev/null 2>&1 || exit 0

# ---- CWD extraction: jq -> python3 -> $PWD fallback chain ----
INPUT=$(cat - 2>/dev/null || true)
CWD=""
if [ -n "$INPUT" ]; then
    if command -v jq >/dev/null 2>&1; then
        CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
    fi
    if [ -z "$CWD" ] && command -v python3 >/dev/null 2>&1; then
        CWD=$(printf '%s' "$INPUT" | python3 -c \
            'import json,sys
try:
    print(json.load(sys.stdin).get("cwd",""))
except Exception:
    print("")' 2>/dev/null || true)
    fi
fi
[ -z "$CWD" ] && CWD="$PWD"

cd "$CWD" 2>/dev/null || exit 0

# ---- Must be a git repo ----
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
[ -z "$BRANCH" ] && exit 0

# ---- Extract issue key from conventional branch name ----
# Pattern: (feat|fix|chore|refactor|test|docs)/PROJ-123[-_/...]
# Uses a case statement for prefix validation (BSD sed does not support | alternation).
_BRANCH_PREFIX="${BRANCH%%/*}"
_BRANCH_REST="${BRANCH#*/}"
ISSUE=""
case "$_BRANCH_PREFIX" in
    feat|fix|chore|refactor|test|docs)
        ISSUE=$(printf '%s' "$_BRANCH_REST" | \
            sed -n -E 's|^([A-Z][A-Z0-9]+-[0-9]+)([-_/].*)?$|\1|p')
        ;;
esac

case "$EVENT" in
    SessionStart)
        [ -z "$ISSUE" ] && exit 0

        # Check whether a timer is already active (any key).
        STATUS=$(tjira timer status --json 2>/dev/null || printf '{}')
        CURRENT=""
        if command -v jq >/dev/null 2>&1; then
            CURRENT=$(printf '%s' "$STATUS" | jq -r '.data.issue_key // empty' 2>/dev/null || true)
        elif command -v python3 >/dev/null 2>&1; then
            CURRENT=$(printf '%s' "$STATUS" | python3 -c \
                'import json,sys
try:
    d=json.load(sys.stdin).get("data") or {}
    print(d.get("issue_key") or "")
except Exception:
    print("")' 2>/dev/null || true)
        fi

        # If any timer is already running, never replace it.
        [ -n "$CURRENT" ] && exit 0

        tjira timer start "$ISSUE" >/dev/null 2>&1 || true
        ;;

    Stop)
        # Stop any active timer. tjira timer stop exits 1 when no timer is
        # active — the hook tolerates that via || true.
        tjira timer stop --json >/dev/null 2>&1 || true
        ;;
esac

exit 0
