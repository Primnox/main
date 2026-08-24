#!/usr/bin/env bash
# Emits one line whenever the newest dispatch changes state: an attempt starting,
# a deliverable landing, the blocker changing, or the run finishing.
# Silent while nothing changes; never silent on failure.
#
# Progress is read from the run directory, not from the process table. A worker
# exits between retries, so process count drops to zero during every backoff gap
# and cannot distinguish "waiting to retry" from "died". Attempt log files can.

RUNS_DIR="${ORCH_RUNS_DIR:-$(dirname "$0")/runs}"
SANDBOX_ROOT="${ORCH_SANDBOX_ROOT:-$LOCALAPPDATA/Temp/ox-orchestrator/sandbox}"
LOG="${ORCH_OPENCODE_LOG:-$HOME/.local/share/opencode/log/opencode.log}"
POLL_S="${ORCH_WATCH_POLL_S:-45}"
SEEDED='AGENTS.md|TASK.md|opencode.json'

run_id="$(ls -t "$RUNS_DIR" 2>/dev/null | head -1)"
[ -z "$run_id" ] && { echo "FATAL no run directory under $RUNS_DIR"; exit 1; }
rundir="$RUNS_DIR/$run_id"
sandbox="$SANDBOX_ROOT/$run_id"
# Derive the worker's model id from the sandbox config so log filtering follows
# whatever was dispatched rather than a value baked in here.
model="$(grep -hoE '"model": *"[^"]+"' "$sandbox"/*/opencode.json 2>/dev/null \
          | head -1 | sed 's/.*: *"//;s/"$//')"
model_id="${model#*/}"
echo "watching run $run_id (model ${model_id:-unknown})"

prev_state=''
prev_files=''

while true; do
  # Deliverables that actually landed, ignoring what we seeded in.
  files="$(find "$sandbox" -type f 2>/dev/null \
            | grep -vE "/($SEEDED)$" \
            | sed "s|^$sandbox/||" | sort)"

  if [ "$files" != "$prev_files" ]; then
    comm -13 <(echo "$prev_files") <(echo "$files") 2>/dev/null \
      | grep -v '^$' | sed 's/^/FILE /'
    prev_files="$files"
  fi

  # One attempt writes one stdout log, so this is the retry counter.
  attempts=''
  for d in "$rundir"/*/; do
    [ -d "$d" ] || continue
    n="$(ls "$d"/stdout*.jsonl 2>/dev/null | wc -l | tr -d ' ')"
    attempts="$attempts $(basename "$d")=$n"
  done

  count="$(echo "$files" | grep -cv '^$')"

  # The runner writes one shared log for every session on this machine, including
  # ones we did not start. Filter to our own model or we report someone else's
  # failures as ours. The id is read from the sandbox config, not hardcoded.
  err="$(grep -F "modelID=$model_id" "$LOG" 2>/dev/null \
          | grep -oE 'Rate limit exceeded[^\"]*|AI_APICallError[^\"]*|stream error' | tail -1)"

  state="attempts:$attempts | deliverables=$count ${err:+| $err}"
  if [ "$state" != "$prev_state" ]; then
    echo "$state"
    prev_state="$state"
  fi

  if [ -f "$rundir/run.json" ]; then
    echo "RUN COMPLETE - $(grep -o '"status": *"[a-z-]*"' "$rundir/run.json" | sed 's/.*: *//' | sort | uniq -c | tr '\n' ' ')"
    exit 0
  fi

  sleep "$POLL_S"
done
