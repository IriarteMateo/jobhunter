#!/usr/bin/env bash
# Actualiza una instalación existente sin perder los empleos guardados,
# aplicados ni descartados.
set -uo pipefail
cd "$(dirname "$0")"

ok()    { printf '  \033[0;32m✓\033[0m %s\n' "$1"; }
falla() { printf '  \033[0;31m✗\033[0m %s\n' "$1"; }
paso()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

clear
printf '\033[1;36m
   ╭────────────────────────────────────────────╮
   │       A I   J O B   H U N T E R            │
   │       actualizar a la última versión       │
   ╰────────────────────────────────────────────╯
\033[0m\n'
echo "  Tus empleos guardados, aplicados y descartados NO se tocan."
echo

paso "1/4  Sacando el bloqueo de macOS"
xattr -dr com.apple.quarantine . 2>/dev/null || true
chmod +x ./*.sh ./*.command 2>/dev/null || true
ok "listo"

paso "2/4  Actualizando dependencias"
VENV=backend/.venv
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import fastapi" >/dev/null 2>&1; then
  "$VENV/bin/pip" install -q -r backend/requirements.txt && ok "backend al día"
else
  rm -rf "$VENV"
  python3 -m venv "$VENV" && "$VENV/bin/pip" install -q --upgrade pip \
    && "$VENV/bin/pip" install -q -r backend/requirements.txt && ok "backend instalado"
fi
(cd frontend && npm install --silent --no-audit --no-fund) && ok "interfaz al día"
rm -rf frontend/.next   # un build viejo sirve estilos que ya no existen
ok "build anterior descartado"

paso "3/4  Buscando empleos"
if [ -f backend/jobhunter.db ]; then
  ok "base existente conservada"
fi
(cd backend && ../"$VENV"/bin/python -m app.seed >/dev/null 2>&1)
RES=$(cd backend && ../"$VENV"/bin/python -m app.daily 2>/dev/null | tail -1)
if echo "$RES" | grep -q "raw_jobs"; then
  C=$(echo "$RES" | sed -n 's/.*"raw_jobs": *\([0-9]*\).*/\1/p')
  N=$(echo "$RES" | sed -n 's/.*"new_jobs": *\([0-9]*\).*/\1/p')
  R=$(echo "$RES" | sed -n 's/.*"recommended": *\([0-9]*\).*/\1/p')
  ok "$C avisos revisados · $N nuevos · $R recomendados"
else
  falla "la búsqueda no terminó bien (podés reintentar desde el botón de la app)"
fi

paso "4/4  Reprogramando la búsqueda diaria"
./install-daily.sh >/dev/null 2>&1 && ok "07:30, todos los días" || falla "no se pudo programar"

paso "Listo. Abriendo la app…"
echo
echo "  → http://localhost:3000"
echo
( sleep 9; open "http://localhost:3000" >/dev/null 2>&1 ) &
exec ./start.sh
