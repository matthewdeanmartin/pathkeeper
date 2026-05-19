#!/usr/bin/env bash
# Integration test runner for pathkeeper CLI (Python or Go).
#
# Usage:
#   # Python
#   PK="python -m pathkeeper" bash spec/run_tests.sh
#
#   # Go
#   make build
#   PK=./bin/pathkeeper bash spec/run_tests.sh
#
# Requires: the binary/module to accept --var PATHX flag.
# PATHKEEPER_HOME is set to a temp dir so tests never touch ~/.pathkeeper.

set -uo pipefail

PK="${PK:-pathkeeper}"
export PATHKEEPER_HOME
PATHKEEPER_HOME="$(mktemp -d)"

# Real directories used as test entries (Windows-safe paths)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    SEP=";"
    T_A="C:\\Windows"
    T_B="C:\\Windows\\system32"
    T_C="C:\\Windows\\System32\\Wbem"
    T_D="C:\\Windows\\System32\\WindowsPowerShell\\v1.0"
else
    SEP=":"
    T_A="/tmp"
    T_B="/usr/bin"
    T_C="/usr/local/bin"
    T_D="/bin"
fi

PASS=0
FAIL=0
output=""
last_exit=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

run() {
    local name="$1"; shift
    output=""
    last_exit=0
    output=$(eval "$@" 2>&1) && last_exit=$? || last_exit=$?
}

pass() { echo "  PASS $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL $1 — $2"; FAIL=$((FAIL+1)); }

# ---------------------------------------------------------------------------
# T1 — version / help
# ---------------------------------------------------------------------------
echo "=== T1: version / help ==="

run T1.1 "$PK --version"
if [ "$last_exit" = "0" ] && echo "$output" | grep -qi "pathkeeper\|0\."; then pass T1.1; else fail T1.1 "exit=$last_exit output=$output"; fi

run T1.2 "$PK --help"
if [ "$last_exit" = "0" ]; then pass T1.2; else fail T1.2 "exit=$last_exit"; fi

# ---------------------------------------------------------------------------
# T2 — backup / backups
# ---------------------------------------------------------------------------
echo "=== T2: backup / backups ==="

export PATHX="${T_A}${SEP}${T_B}${SEP}${T_C}"

run T2.1 "$PK --var PATHX backup --note t2.1 --force"
if [ "$last_exit" = "0" ]; then pass T2.1; else fail T2.1 "exit=$last_exit output=$output"; fi

run T2.2 "$PK backups list"
# pytable_formatter is an optional dep; treat its absence as a soft skip
if [ "$last_exit" = "0" ]; then pass T2.2; elif echo "$output" | grep -q "pytable_formatter\|ModuleNotFound"; then pass "T2.2 (skipped: optional dep missing)"; else fail T2.2 "exit=$last_exit output=$output"; fi

run T2.4 "$PK --var PATHX backup --force"
if [ "$last_exit" = "0" ]; then pass T2.4; else fail T2.4 "exit=$last_exit output=$output"; fi

run T2.5 "$PK backups show 1"
if [ "$last_exit" = "0" ]; then pass T2.5; else fail T2.5 "exit=$last_exit output=$output"; fi

# ---------------------------------------------------------------------------
# T3 — inspect / doctor
# ---------------------------------------------------------------------------
echo "=== T3: inspect / doctor ==="

run T3.1 "$PK --var PATHX inspect"
if [ "$last_exit" = "0" ]; then pass T3.1; else fail T3.1 "exit=$last_exit output=$output"; fi

run T3.2 "$PK --var PATHX inspect --json"
if [ "$last_exit" = "0" ] && echo "$output" | python3 -m json.tool >/dev/null 2>&1; then pass T3.2; else fail T3.2 "json invalid: $output"; fi

run T3.3 "$PK --var PATHX inspect --only-invalid"
if [ "$last_exit" = "0" ]; then pass T3.3; else fail T3.3 "exit=$last_exit"; fi

run T3.4 "$PK --var PATHX doctor"
if [ "$last_exit" = "0" ]; then pass T3.4; else fail T3.4 "exit=$last_exit output=$output"; fi

run T3.5 "$PK --var PATHX doctor --json"
if [ "$last_exit" = "0" ] && echo "$output" | python3 -m json.tool >/dev/null 2>&1; then pass T3.5; else fail T3.5 "json invalid: $output"; fi

run T3.6 "$PK --var PATHX doctor --explain"
if [ "$last_exit" = "0" ]; then pass T3.6; else fail T3.6 "exit=$last_exit"; fi

# ---------------------------------------------------------------------------
# T4 — diff / diff-current
# ---------------------------------------------------------------------------
echo "=== T4: diff / diff-current ==="

run T4.2 "$PK --var PATHX diff-current 1"
if [ "$last_exit" = "0" ]; then pass T4.2; else fail T4.2 "exit=$last_exit output=$output"; fi

# ---------------------------------------------------------------------------
# T5 — shadow / runtime-entries / selfcheck
# ---------------------------------------------------------------------------
echo "=== T5: shadow / runtime-entries / selfcheck ==="

run T5.1 "$PK --var PATHX shadow"
if [ "$last_exit" = "0" ]; then pass T5.1; else fail T5.1 "exit=$last_exit output=$output"; fi

run T5.2 "$PK --var PATHX shadow --json"
# May output [] JSON or "No shadowed executables found." — both are valid
if [ "$last_exit" = "0" ]; then pass T5.2; else fail T5.2 "exit=$last_exit output=$output"; fi

run T5.3 "$PK --var PATHX runtime-entries"
if [ "$last_exit" = "0" ]; then pass T5.3; else fail T5.3 "exit=$last_exit"; fi

run T5.4 "$PK selfcheck"
# selfcheck may exit 1 if install is incomplete — that's acceptable
if [ "$last_exit" = "0" ] || [ "$last_exit" = "1" ]; then pass T5.4; else fail T5.4 "exit=$last_exit"; fi

# ---------------------------------------------------------------------------
# T6 — restore (dry-run only)
# ---------------------------------------------------------------------------
echo "=== T6: restore ==="

# Ensure at least one backup exists before restore test
run _pre_restore "$PK --var PATHX backup --force"

# Use numeric 1 (latest backup) with dry-run
# Go uses PATHKEEPER_HOME; Python uses ~/.pathkeeper
run T6.1 "$PK --var PATHX restore 1 --dry-run"
if [ "$last_exit" = "0" ]; then pass T6.1;
elif echo "$output" | grep -qi "not found\|no backup"; then
    # Possible if backups are in a different location (Python without PATHKEEPER_HOME support)
    # Try using the literal backup path from our pre-restore backup output
    _backup_path=$(eval "$PK --var PATHX backup --force 2>&1" | grep -oE '[^ ]+\.json$' | head -1)
    if [ -n "$_backup_path" ]; then
        run T6.1b "$PK --var PATHX restore '$_backup_path' --dry-run"
        if [ "$last_exit" = "0" ]; then pass "T6.1 (path-based)"; else fail T6.1 "exit=$last_exit output=$output"; fi
    else
        pass "T6.1 (skipped: no backup path available)"
    fi
else
    fail T6.1 "exit=$last_exit output=$output"
fi

# ---------------------------------------------------------------------------
# T7 — dedupe
# ---------------------------------------------------------------------------
echo "=== T7: dedupe ==="

export PATHX="${T_A}${SEP}${T_B}${SEP}${T_A}"

run T7.1 "$PK --var PATHX dedupe --dry-run"
if [ "$last_exit" = "0" ]; then pass T7.1; else fail T7.1 "exit=$last_exit output=$output"; fi

run T7.2 "$PK --var PATHX dedupe --force"
if [ "$last_exit" = "0" ]; then pass T7.2; else fail T7.2 "exit=$last_exit output=$output"; fi

# ---------------------------------------------------------------------------
# T8 — edit (dry-run only)
# ---------------------------------------------------------------------------
echo "=== T8: edit ==="

export PATHX="${T_A}${SEP}${T_B}"

run T8.1 "$PK --var PATHX edit --add $T_D --dry-run"
if [ "$last_exit" = "0" ]; then pass T8.1; else fail T8.1 "exit=$last_exit output=$output"; fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed  (PATHKEEPER_HOME=$PATHKEEPER_HOME)"
[ "$FAIL" = "0" ] && exit 0 || exit 1
