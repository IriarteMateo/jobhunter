#!/usr/bin/env bash
set -euo pipefail
LABEL="com.jobhunter.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "✓ Búsqueda diaria desinstalada. La app sigue funcionando normalmente."
