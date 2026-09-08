#!/usr/bin/env bash
# Programa la actualización automática: cada 10 minutos busca mejoras nuevas.
# Se instala una sola vez. Para sacarlo: ./uninstall-auto-update.sh
set -euo pipefail
cd "$(dirname "$0")"
RAIZ="$(pwd)"

LABEL="com.jobhunter.autoupdate"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" logs

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$RAIZ/auto-update.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$RAIZ</string>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>$RAIZ/logs/auto-update.err</string>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✓ Actualización automática activada (cada 10 minutos)."
echo "  Registro: $RAIZ/logs/auto-update.log"
