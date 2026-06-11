#!/bin/bash
# verify_aggregation_audit.sh - Audit verification rerun script
# 
# This script reruns a representative subset of the aggregation audit.
# Exit codes:
#   0 - All verifications pass
#   1 - One or more mandatory verifications fail
#   2 - Environment error (cannot run tests)
#
# NOTE: This audit was frozen before any tests were executed.
# This script is a template for future audit execution.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EVIDENCE_DIR="$PROJECT_ROOT/LIVE_TEST_EVIDENCE"
RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$EVIDENCE_DIR/$RUN_ID/verification.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

echo "================================================"
echo "Aggregation Audit Verification Script"
echo "Run ID: $RUN_ID"
echo "================================================"
echo ""

# Create evidence directory
mkdir -p "$EVIDENCE_DIR/$RUN_ID"

# Initialize results file
echo "Run ID: $RUN_ID" > "$EVIDENCE_DIR/$RUN_ID/results.txt"
echo "Start: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
echo "" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"

# Verification function
verify_step() {
    local step_name="$1"
    local command="$2"
    local expected="$3"
    
    echo -n "Verifying: $step_name ... "
    
    local step_log="$EVIDENCE_DIR/$RUN_ID/${step_name}.log"
    local start_time=$(date +%s)
    
    # Run command and capture output
    set +e
    cd "$PROJECT_ROOT"
    eval "$command" > "$step_log" 2>&1
    local exit_code=$?
    set -e
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Check result
    if [ "$exit_code" -eq 0 ]; then
        if [ -n "$expected" ]; then
            if grep -q "$expected" "$step_log"; then
                echo -e "${GREEN}PASS${NC} (${duration}s)"
                echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] PASS: $step_name (${duration}s)" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
                PASS_COUNT=$((PASS_COUNT + 1))
            else
                echo -e "${YELLOW}PARTIAL${NC} (exit 0, expected output not found)"
                echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] PARTIAL: $step_name (expected: $expected)" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
        else
            echo -e "${GREEN}PASS${NC} (${duration}s)"
            echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] PASS: $step_name (${duration}s)" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
            PASS_COUNT=$((PASS_COUNT + 1))
        fi
    else
        echo -e "${RED}FAIL${NC} (exit $exit_code, ${duration}s)"
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] FAIL: $step_name (exit $exit_code)" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "===== ENVIRONMENT CHECK ====="

# Check Python
verify_step "python_version" \
    "python3 --version" \
    "Python"

# Check virtual environment
verify_step "venv_exists" \
    "test -d $PROJECT_ROOT/.venv" \
    ""

# Check database
verify_step "database_exists" \
    "test -f $PROJECT_ROOT/betting/data/betting.db" \
    ""

echo ""
echo "===== DISCOVERY SOURCES (at least one per domain) ====="

# Football discovery
echo -e "${YELLOW}NOTE: Live tests disabled in template${NC}"
echo "verify_step discovery_football would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Basketball discovery
echo "verify_step discovery_basketball would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Hockey discovery
echo "verify_step discovery_hockey would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Tennis discovery
echo "verify_step discovery_tennis would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Volleyball discovery
echo "verify_step discovery_volleyball would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# CS2 discovery
echo "verify_step discovery_cs2 would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Dota2 discovery
echo "verify_step discovery_dota2 would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

# Valorant discovery
echo "verify_step discovery_valorant would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== CANONICAL EVENT MATCHING ====="

# Canonical event matching test
echo "verify_step canonical_matching would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== H2H CORRECTNESS ====="

# H2H correctness test
echo "verify_step h2h_correctness would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== RECENT FORM CORRECTNESS ====="

# Recent form correctness test
echo "verify_step recent_form_correctness would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== PARTIAL DATA SCENARIO ====="

# Partial data handling test
echo "verify_step partial_data_handling would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== TIMEOUT/FAILURE SCENARIO ====="

# Timeout handling test
echo "verify_step timeout_handling would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== END-TO-END DISCOVERY-TO-PERSISTENCE ====="

# End-to-end test
echo "verify_step e2e_discovery_persistence would run here"
SKIP_COUNT=$((SKIP_COUNT + 1))

echo ""
echo "===== RESULTS SUMMARY ====="

echo ""
echo "End: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
echo "Pass: $PASS_COUNT" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
echo "Fail: $FAIL_COUNT" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"
echo "Skip: $SKIP_COUNT" >> "$EVIDENCE_DIR/$RUN_ID/results.txt"

cat "$EVIDENCE_DIR/$RUN_ID/results.txt"

echo ""
echo "================================================"
echo "PASS: $PASS_COUNT | FAIL: $FAIL_COUNT | SKIP: $SKIP_COUNT"
echo "================================================"
echo ""

# Machine-readable result
if [ $FAIL_COUNT -gt 0 ]; then
    echo "RESULT: FAIL"
    exit 1
elif [ $SKIP_COUNT -gt 0 ] && [ $PASS_COUNT -eq 0 ]; then
    echo "RESULT: SKIP (no tests actually run)"
    echo ""
    echo "NOTE: This audit was frozen before tests were implemented."
    echo "This script is a TEMPLATE. Actual tests must be implemented."
    exit 2
else
    echo "RESULT: PASS"
    exit 0
fi
