#!/usr/bin/env bash
# Instala la búsqueda diaria como agente de macOS (launchd).
#
# A diferencia del scheduler interno de la app, esto corre AUNQUE LA APP ESTÉ
# CERRADA. launchd además recupera las corridas perdidas: si la Mac estaba
# dormida a la hora programada, la ejecuta apenas despierta.
set -euo pipefail
cd "$(dirname "$0")"

ROOT="$(pwd)"
LABEL="com.jobhunter.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$ROOT/backend/.venv/bin/python"
HOUR="${1:-7}"
MINUTE="${2:-30}"

if [ ! -x "$PYTHON" ]; then
  echo "✗ No encuentro el entorno virtual en $PYTHON"
  echo "  Corré ./start.sh una vez para crearlo."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/backend/logs"

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
        <string>$PYTHON</string>
        <string>-m</string>
        <string>app.daily</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$ROOT/backend</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$HOUR</integer>
        <key>Minute</key><integer>$MINUTE</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$ROOT/backend/logs/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/backend/logs/launchd.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

printf '✓ Búsqueda diaria instalada a las %02d:%02d\n\n' "$HOUR" "$MINUTE"
echo "  Corre aunque la app esté cerrada. Si la Mac está dormida a esa hora,"
echo "  launchd la ejecuta apenas despierta."
echo
echo "  Probar ahora      : launchctl start $LABEL"
echo "  Ver el registro   : tail -f $ROOT/backend/logs/daily.log"
echo "  Ver estado        : launchctl list | grep jobhunter"
echo "  Desinstalar       : ./uninstall-daily.sh"
