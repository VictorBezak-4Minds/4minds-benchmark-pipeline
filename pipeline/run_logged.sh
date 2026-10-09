#!/bin/zsh
# Run one benchmark step and record it in <benchmark>/results/audit/audit.log.
# ./bench calls this script; it sets BENCH_DIR.
#   run_logged.sh <step-name> <command> [args...]
# The full output of the step goes to results/audit/steps/<timestamp>_<step-name>.log
# and also to the terminal. The exit code of the command is kept.
set -u
: "${BENCH_DIR:?BENCH_DIR is not set. Use ./bench <benchmark> <step> <env> <script> [args].}"
AUDIT="$BENCH_DIR/results/audit"
mkdir -p "$AUDIT/steps"

STEP="$1"; shift
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$AUDIT/steps/${STAMP}_${STEP}.log"

record() {
  # One write per record: steps that start at the same time append to the same file.
  python3 -c 'import json,sys; sys.stdout.write(json.dumps(dict(zip(sys.argv[1::2], sys.argv[2::2]))) + "\n")' "$@" >> "$AUDIT/audit.log"
}

START_EPOCH="$(date +%s)"
record time "$(date -u +%FT%TZ)" event step_start step "$STEP" benchmark "${BENCHMARK:-}" command "$*" log "$LOG"
{ echo "# step: $STEP"; echo "# start: $(date -u +%FT%TZ)"; echo "# command: $*"; echo; } > "$LOG"

"$@" 2>&1 | tee -a "$LOG"
CODE="${pipestatus[1]}"

DURATION="$(( $(date +%s) - START_EPOCH ))"
{ echo; echo "# end: $(date -u +%FT%TZ)  exit: $CODE  duration_s: $DURATION"; } >> "$LOG"
record time "$(date -u +%FT%TZ)" event step_end step "$STEP" exit_code "$CODE" duration_s "$DURATION" log "$LOG"
exit "$CODE"
