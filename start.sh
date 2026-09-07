#!/usr/bin/env bash
# Levanta backend y frontend. Ctrl+C corta ambos.
#
# Usa el modo desarrollo de Next.js a propósito: recompila solo cuando cambia un
# archivo y nunca queda sirviendo el índice de un build viejo.
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT=8080
FRONTEND_PORT=3000
VENV=backend/.venv

# ----------------------------------------------------------- requisitos ---
faltan=()
command -v python3 >/dev/null 2>&1 || faltan+=("Python 3.12+ · https://www.python.org/downloads/")
command -v node    >/dev/null 2>&1 || faltan+=("Node.js 20+ · https://nodejs.org/")
command -v npm     >/dev/null 2>&1 || faltan+=("npm (viene con Node.js)")
if [ ${#faltan[@]} -gt 0 ]; then
  echo "✗ Falta instalar:"
  printf '    · %s\n' "${faltan[@]}"
  exit 1
fi

# ------------------------------------------------------ puertos libres ----
free_port() {
  local port=$1 pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "→ liberando el puerto $port"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    # shellcheck disable=SC2086
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}
free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

# ------------------------------------------------------------- backend ---
# Un .venv copiado de otra computadora tiene rutas absolutas de esa máquina y
# no arranca. Se detecta probándolo, y si está roto se rehace.
venv_sirve() {
  [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import fastapi" >/dev/null 2>&1
}
if ! venv_sirve; then
  if [ -d "$VENV" ]; then
    echo "→ el entorno de Python no sirve en esta computadora: lo rehago…"
    rm -rf "$VENV"
  else
    echo "→ creando el entorno de Python…"
  fi
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r backend/requirements.txt
fi

# ------------------------------------------------------------ frontend ---
if [ ! -d frontend/node_modules ]; then
  echo "→ instalando dependencias del frontend (tarda un rato la primera vez)…"
  (cd frontend && npm install)
fi

# --------------------------------------------------------------- listo ---
echo "→ backend  http://127.0.0.1:$BACKEND_PORT   (documentación en /docs)"
(cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT") &
BACKEND_PID=$!

echo "→ frontend http://localhost:$FRONTEND_PORT"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo
echo "   Abrí →  http://localhost:$FRONTEND_PORT"
echo

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  free_port "$BACKEND_PORT"
  free_port "$FRONTEND_PORT"
}
trap cleanup EXIT INT TERM
wait
