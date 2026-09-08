#!/usr/bin/env bash
# Desactiva la actualización automática. La app sigue funcionando igual.
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.jobhunter.autoupdate.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "✓ Actualización automática desactivada."
