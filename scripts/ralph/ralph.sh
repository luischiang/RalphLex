#!/bin/bash
# Ralph Wiggum - Long-running AI agent loop
# Usage: ./ralph.sh [--tool amp|claude] [max_iterations]

set -e

# Parse arguments
TOOL="amp"  # Default to amp for backwards compatibility
MAX_ITERATIONS=10

while [[ $# -gt 0 ]]; do
  case $1 in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    *)
      # Assume it's max_iterations if it's a number
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

# Validate tool choice
if [[ "$TOOL" != "amp" && "$TOOL" != "claude" ]]; then
  echo "Error: Invalid tool '$TOOL'. Must be 'amp' or 'claude'."
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

# Archive previous run if branch changed
if [ -f "$PRD_FILE" ] && [ -f "$LAST_BRANCH_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")
  
  if [ -n "$CURRENT_BRANCH" ] && [ -n "$LAST_BRANCH" ] && [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
    # Archive the previous run
    DATE=$(date +%Y-%m-%d)
    # Strip "ralph/" prefix from branch name for folder
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|^ralph/||')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"
    
    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PRD_FILE" ] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    echo "   Archived to: $ARCHIVE_FOLDER"
    
    # Reset progress file for new run
    echo "# Ralph Progress Log" > "$PROGRESS_FILE"
    echo "Started: $(date)" >> "$PROGRESS_FILE"
    echo "---" >> "$PROGRESS_FILE"
  fi
fi

# Track current branch
if [ -f "$PRD_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  if [ -n "$CURRENT_BRANCH" ]; then
    echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"
  fi
fi

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

# Completion is decided by the PRD, never by text in the agent's output. An agent
# that merely mentions the completion token while explaining that it is NOT done
# used to end the whole run.
all_stories_pass() {
  jq -e '[(.stories // .userStories)[] | .passes] | length > 0 and all' "$PRD_FILE" >/dev/null 2>&1
}

stories_passing() {
  jq -r '[(.stories // .userStories)[] | select(.passes)] | length' "$PRD_FILE" 2>/dev/null || echo 0
}

if all_stories_pass; then
  echo "All stories already pass. Nothing to do."
  exit 0
fi

echo "Starting Ralph - Tool: $TOOL - Max iterations: $MAX_ITERATIONS"

NO_PROGRESS_STREAK=0

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "==============================================================="
  echo "  Ralph Iteration $i of $MAX_ITERATIONS ($TOOL)"
  echo "==============================================================="

  BEFORE_HEAD=$(git rev-parse HEAD 2>/dev/null || echo none)
  BEFORE_PASSING=$(stories_passing)

  # Run the selected tool with the ralph prompt. The exit status is captured
  # rather than discarded: a crashing agent must not look like a completed one.
  set +e
  if [[ "$TOOL" == "amp" ]]; then
    amp --dangerously-allow-all < "$SCRIPT_DIR/prompt.md" 2>&1 | tee /dev/stderr
    STATUS=${PIPESTATUS[0]}
  else
    # Claude Code: --dangerously-skip-permissions for autonomous operation.
    # Under root (containers, CI) this flag needs IS_SANDBOX=1 or it refuses to start.
    claude --dangerously-skip-permissions --print < "$SCRIPT_DIR/CLAUDE.md" 2>&1 | tee /dev/stderr
    STATUS=${PIPESTATUS[0]}
  fi
  set -e

  if [ "$STATUS" -ne 0 ]; then
    echo ""
    echo "Iteration $i: $TOOL exited with status $STATUS."
    echo "Aborting rather than spinning through the remaining iterations."
    exit "$STATUS"
  fi

  if all_stories_pass; then
    echo ""
    echo "Ralph completed all tasks!"
    echo "Completed at iteration $i of $MAX_ITERATIONS"
    exit 0
  fi

  # A no-op iteration means the agent changed nothing: no commit, no story
  # advanced. Two in a row means the loop is stuck, not working.
  AFTER_HEAD=$(git rev-parse HEAD 2>/dev/null || echo none)
  AFTER_PASSING=$(stories_passing)

  if [ "$AFTER_HEAD" = "$BEFORE_HEAD" ] && [ "$AFTER_PASSING" = "$BEFORE_PASSING" ]; then
    NO_PROGRESS_STREAK=$((NO_PROGRESS_STREAK + 1))
    echo "Iteration $i made no progress (no new commit, no story advanced)."
    if [ "$NO_PROGRESS_STREAK" -ge 2 ]; then
      echo "Two consecutive iterations without progress. Aborting."
      exit 1
    fi
  else
    NO_PROGRESS_STREAK=0
    echo "Iteration $i complete ($AFTER_PASSING stories passing). Continuing..."
  fi

  sleep 2
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "$(stories_passing) stories passing. Check $PROGRESS_FILE for status."
exit 1
