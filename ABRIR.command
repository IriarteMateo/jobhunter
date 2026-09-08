#!/bin/bash
# ============================================================================
#  AI Job Hunter — ABRIR LA APP
#
#  Doble clic en este archivo. Nada más.
#
#  Sirve para todo: la primera vez instala y busca empleos, y de ahí en
#  adelante simplemente abre la app. No hay que elegir entre varios scripts.
#  Se puede correr las veces que haga falta: si algo ya está hecho, lo saltea.
# ============================================================================

cd "$(dirname "$0")" || exit 1
RAIZ="$(pwd)"
VENV="backend/.venv"

# macOS marca los archivos bajados de internet. Sin esto, "no se puede abrir".
xattr -dr com.apple.quarantine . 2>/dev/null

azul()  { printf '\n\033[1;34m%s\033[0m\n' "$1"; }
ok()    { printf '   \033[32m✓\033[0m %s\n' "$1"; }
info()  { printf '     %s\n' "$1"; }

# Cualquier error corta acá y explica, en vez de cerrar la ventana de golpe.
morir() {
  printf '\n\033[1;31m  ✗ %s\033[0m\n\n' "$1"
  shift
  for l in "$@"; do printf '    %s\n' "$l"; done
  printf '\n    La ventana queda abierta para que puedas leer esto.\n'
  printf '    Si no se entiende, sacale una foto y mandásela a Mateo.\n\n'
  read -r -p "    Apretá Enter para cerrar. " _
  exit 1
}

printf '\033[2J\033[H'
cat <<'BANNER'
  ┌──────────────────────────────────────────┐
  │        AI  JOB  HUNTER                   │
  │        Buscador de empleos               │
  └──────────────────────────────────────────┘
BANNER
echo "  Carpeta: $RAIZ"

# ---------------------------------------------------------------------------
# 1. ¿Están Python y Node?  Es lo que más falla en una Mac nueva.
# ---------------------------------------------------------------------------
azul "1/5  Revisando qué hay instalado"

if ! command -v python3 >/dev/null 2>&1; then
  morir "Falta Python 3" \
    "Abrí esta página y descargá el instalador para macOS:" \
    "" \
    "    https://www.python.org/downloads/" \
    "" \
    "Instalalo, y después volvé a hacer doble clic en ABRIR.command."
fi
ok "Python $(python3 -V 2>&1 | awk '{print $2}')"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo
  printf '  \033[1;33mFalta Node.js\033[0m — es lo que dibuja la pantalla de la app.\n'
  info "No viene puesto en las Mac, hay que instalarlo una sola vez."
  echo
  read -r -p "    ¿Te abro la página de descarga? [S/n] " r
  if [ "$r" != "n" ] && [ "$r" != "N" ]; then
    open "https://nodejs.org/en/download" 2>/dev/null
  fi
  morir "Instalá Node.js y volvé a abrir este archivo" \
    "En la página, bajá el instalador para macOS y hacé doble clic." \
    "Aceptá todo lo que te pregunte." \
    "" \
    "Cuando termine, doble clic de nuevo en ABRIR.command."
fi
ok "Node $(node -v)"

# ---------------------------------------------------------------------------
# 2. Dependencias. Solo la primera vez, o si el entorno vino de otra Mac.
# ---------------------------------------------------------------------------
azul "2/5  Preparando el programa"

venv_sirve() { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import fastapi" >/dev/null 2>&1; }

if venv_sirve; then
  ok "motor de búsqueda listo"
else
  # Un .venv copiado de otra computadora guarda rutas de esa máquina y no arranca.
  [ -d "$VENV" ] && { info "el entorno no sirve en esta Mac, lo rehago…"; rm -rf "$VENV"; } \
                 || info "instalando el motor (un par de minutos la primera vez)…"
  python3 -m venv "$VENV" \
    || morir "No pude crear el entorno de Python" "Probá instalando Python de nuevo desde python.org."
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r backend/requirements.txt \
    || morir "No pude instalar las dependencias de Python" "Fijate que tengas internet y volvé a intentar."
  ok "motor de búsqueda instalado"
fi

if [ -d frontend/node_modules ]; then
  ok "pantalla lista"
else
  info "instalando la pantalla (tarda unos minutos la primera vez)…"
  ( cd frontend && npm install --silent --no-audit --no-fund ) \
    || morir "No pude instalar la pantalla" "Fijate que tengas internet y volvé a intentar."
  ok "pantalla instalada"
fi

# ---------------------------------------------------------------------------
# 3. Base de datos y primera búsqueda, solo si está vacía.
# ---------------------------------------------------------------------------
azul "3/5  Empleos"

CUANTOS=$( cd backend && ../"$VENV"/bin/python -c "
try:
    from app.db import SessionLocal
    from app.models import Job
    from sqlalchemy import select, func
    print(SessionLocal().scalar(select(func.count(Job.id))) or 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0 )

if [ "${CUANTOS:-0}" -gt 0 ]; then
  ok "$CUANTOS empleos ya guardados"
  info "la búsqueda de cada día los va actualizando sola"
else
  info "primera búsqueda: reviso unas 74 fuentes, tarda 2 o 3 minutos…"
  ( cd backend && ../"$VENV"/bin/python -m app.seed ) >/dev/null 2>&1
  ( cd backend && ../"$VENV"/bin/python -m app.daily ) 2>/dev/null | tail -1 | sed 's/^/     /'
  NUEVOS=$( cd backend && ../"$VENV"/bin/python -c "
from app.db import SessionLocal
from app.models import Job
from sqlalchemy import select, func
print(SessionLocal().scalar(select(func.count(Job.id))) or 0)" 2>/dev/null || echo 0 )
  if [ "${NUEVOS:-0}" -gt 0 ]; then
    ok "$NUEVOS empleos encontrados"
  else
    info "no encontré empleos ahora; podés reintentar desde el botón de la app"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Búsqueda automática diaria.
# ---------------------------------------------------------------------------
azul "4/5  Automatismos"
if [ -f "$HOME/Library/LaunchAgents/com.jobhunter.daily.plist" ]; then
  ok "búsqueda diaria ya programada (07:30)"
else
  ./install-daily.sh >/dev/null 2>&1 && ok "búsqueda diaria programada (07:30)" \
    || info "no se pudo programar; la app funciona igual con el botón de buscar"
fi

# Las mejoras llegan solas desde GitHub. Sólo si la carpeta es un repo.
if [ -d .git ]; then
  if [ -f "$HOME/Library/LaunchAgents/com.jobhunter.autoupdate.plist" ]; then
    ok "mejoras automáticas ya activadas"
  else
    ./install-auto-update.sh >/dev/null 2>&1 && ok "mejoras automáticas activadas" \
      || info "no se pudieron activar; la app funciona igual"
  fi
fi

# ---------------------------------------------------------------------------
# 5. A andar.
# ---------------------------------------------------------------------------
azul "5/5  Abriendo la app"

liberar() {
  local pids; pids=$(lsof -ti :"$1" 2>/dev/null)
  [ -n "$pids" ] && { kill $pids 2>/dev/null; sleep 1; pids=$(lsof -ti :"$1" 2>/dev/null); [ -n "$pids" ] && kill -9 $pids 2>/dev/null; }
  return 0
}
liberar 8080
liberar 3000

# --reload: cuando la actualización automática trae código nuevo, el backend
# lo toma solo, sin cerrar y volver a abrir la app.
( cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --log-level warning --reload --reload-dir app ) >/dev/null 2>&1 &
PID_BACK=$!
( cd frontend && npm run dev ) >/dev/null 2>&1 &
PID_FRONT=$!

limpiar() { kill "$PID_BACK" "$PID_FRONT" 2>/dev/null; liberar 8080; liberar 3000; }
trap limpiar EXIT INT TERM

printf '     esperando'
LISTA=no
for _ in $(seq 60); do
  printf '.'
  if curl -s -m 2 http://localhost:3000 >/dev/null 2>&1 \
     && curl -s -m 2 http://localhost:8080/api/health >/dev/null 2>&1; then
    LISTA=si; break
  fi
  sleep 2
done
echo

if [ "$LISTA" = no ]; then
  morir "La app tardó demasiado en levantar" \
    "Cerrá esta ventana y volvé a hacer doble clic en ABRIR.command." \
    "Si vuelve a pasar, mandale una foto de esta pantalla a Mateo."
fi

open "http://localhost:3000" 2>/dev/null

cat <<'FIN'

  ┌──────────────────────────────────────────┐
  │  LISTO — la app está abierta             │
  │                                          │
  │  Si se cerró:  http://localhost:3000     │
  └──────────────────────────────────────────┘

  ⚠️  NO cierres esta ventana mientras uses la app.
      Para cerrarla del todo: Control + C acá.

  Mañana, para volver a abrirla: doble clic en ABRIR.command.

FIN

wait
