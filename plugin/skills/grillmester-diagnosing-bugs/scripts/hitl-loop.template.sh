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
#   capture_signal VAR "<question>" -> read one already-redacted signal into VAR
#
# Never enter raw logs, HAR content, secrets, auth headers, cookies, tokens or
# personal data. At the end only the bounded signals are printed for parsing.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture_signal() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  printf '    Enter one sanitized signal; replace sensitive values with <REDACTED>.\n'
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below ---------------------------------------------------------

step "Start the affected system with the repository's discovered local command, or connect to an explicitly approved test environment."

capture_signal STATUS "Which HTTP status did the bounded check return?"

capture_signal ERROR "Which redacted error type or code identifies the symptom? Do not paste a log line."

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'STATUS=%s\n' "$STATUS"
printf 'ERROR=%s\n' "$ERROR"
