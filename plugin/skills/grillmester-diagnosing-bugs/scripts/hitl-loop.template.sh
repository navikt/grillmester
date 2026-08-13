#!/usr/bin/env bash
# Human-in-the-loop reproduction loop (last resort in phase 1).
# Copy this file, edit the steps below, and run it.
# The agent runs the script; the user follows the prompts in their own terminal.
#
# Usage:
#   bash hitl-loop.template.sh
#
# Two helpers:
#   step "<instruction>"       -> show the instruction, wait for Enter
#   capture VAR "<question>"   -> show the question, read the answer into VAR
#
# At the end the captured values are printed as KEY=VALUE for the agent to parse.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below ---------------------------------------------------------

step "Start the affected system with the repository's discovered local command, or connect to an explicitly approved test environment."

capture STATUS "curl -s -o /dev/null -w '%{http_code}' against the failing route. Which HTTP status?"

capture ERROR "Paste the error message from the app log (or 'none'):"

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'STATUS=%s\n' "$STATUS"
printf 'ERROR=%s\n' "$ERROR"
