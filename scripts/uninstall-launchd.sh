#!/bin/sh
# Kronos launchd 서비스 제거.
set -eu

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

for label in com.kronos.runner com.kronos.backup; do
  launchctl bootout "gui/$UID/$label" 2>/dev/null && echo "booted out: $label" || true
  rm -f "$LAUNCH_AGENTS_DIR/$label.plist"
  echo "removed: $label"
done
