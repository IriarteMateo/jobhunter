#!/usr/bin/env bash
# Instalación completa: deja la app igual que en la máquina de origen.
#
# A diferencia de start.sh (que sólo levanta lo que ya está instalado), esto
# hace el recorrido entero: dependencias, base, PRIMERA BÚSQUEDA con empleos
# reales, agente diario de las 07:30 y la app abierta en el navegador.
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

azul()  { printf '\033[1;36m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[0;32m✓\033[0m %s\n' "$1"; }
falla() { printf '  \033[0;31m✗\033[0m %s\n' "$1"; }
paso()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

clear
azul "
   ╭────────────────────────────────────────────╮
   │          A I   J O B   H U N T E R         │
   │        instalación completa                │
   ╰────────────────────────────────────────────╯
"
echo "  Esto deja todo listo: la app, los empleos ya cargados,"
echo "  la búsqueda automática diaria y los avisos en pantalla."
echo
echo "  Tarda entre 5 y 10 minutos la primera vez. Podés dejarlo corriendo."
echo

# ─────────────────────────────────────────────── 1. requisitos ───
paso "1/6  Revisando qué hace falta"
faltan=()
command -v python3 >/dev/null 2>&1 || faltan+=("Python 3.12 o superior|https://www.python.org/downloads/")
command -v node    >/dev/null 2>&1 || faltan+=("Node.js 20 o superior|https://nodejs.org/")
if [ ${#faltan[@]} -gt 0 ]; then
  falla "Falta instalar:"
  for f in "${faltan[@]}"; do
    printf '      · %s\n        %s\n' "${f%%|*}" "${f##*|}"
  done
  echo
  echo "  Instalalos, cerrá la Terminal, abrila de nuevo y volvé a correr esto."
  exit 1
fi
ok "Python $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
ok "Node $(node --version)"

# ─────────────────────────────────────────── 2. quitar bloqueo ───
paso "2/6  Sacando el bloqueo de macOS a los archivos descargados"
xattr -dr com.apple.quarantine . 2>/dev/null || true
chmod +x ./*.sh ./*.command 2>/dev/null || true
ok "listo"

# ──────────────────────────────────────────────── 3. backend ───
paso "3/6  Instalando el motor de búsqueda (Python)"
VENV=backend/.venv
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import fastapi" >/dev/null 2>&1; then
  ok "ya estaba instalado"
else
  rm -rf "$VENV"
  python3 -m venv "$VENV" || { falla "no se pudo crear el entorno de Python"; exit 1; }
  "$VENV/bin/pip" install -q --upgrade pip
  echo "  descargando dependencias, esto tarda un poco…"
  "$VENV/bin/pip" install -q -r backend/requirements.txt || { falla "fallaron las dependencias"; exit 1; }
  ok "instalado"
fi

# ─────────────────────────────────────────────── 4. frontend ───
paso "4/6  Instalando la interfaz (Node)"
if [ -d frontend/node_modules ]; then
  ok "ya estaba instalada"
else
  echo "  descargando dependencias, esto tarda un poco…"
  (cd frontend && npm install --silent --no-audit --no-fund) || { falla "falló npm install"; exit 1; }
  ok "instalada"
fi

# ───────────────────────────── 5. base + primera búsqueda real ───
paso "5/6  Buscando empleos por primera vez"
echo "  Consulta más de 70 fuentes reales. Tarda unos 2 minutos."
(cd backend && ../"$VENV"/bin/python -m app.seed >/dev/null 2>&1)
RESULTADO=$(cd backend && ../"$VENV"/bin/python -m app.daily 2>/dev/null | tail -1)
if echo "$RESULTADO" | grep -q "raw_jobs"; then
  CRUDOS=$(echo "$RESULTADO" | sed -n 's/.*"raw_jobs": *\([0-9]*\).*/\1/p')
  NUEVOS=$(echo "$RESULTADO" | sed -n 's/.*"new_jobs": *\([0-9]*\).*/\1/p')
  RECOM=$(echo "$RESULTADO" | sed -n 's/.*"recommended": *\([0-9]*\).*/\1/p')
  ok "$CRUDOS avisos revisados · $NUEVOS relevantes · $RECOM recomendados"
else
  falla "la primera búsqueda no terminó bien (la app funciona igual)"
  echo "      podés reintentar después desde el botón 'Buscar nuevos empleos ahora'"
fi

# ──────────────────────────────────────── 6. búsqueda diaria ───
paso "6/6  Programando la búsqueda automática de las 07:30"
if ./install-daily.sh >/dev/null 2>&1; then
  ok "queda corriendo sola todos los días, aunque la app esté cerrada"
else
  falla "no se pudo programar (la app funciona igual)"
fi

# ───────────────────────────────────────────────── arrancar ───
paso "Listo. Abriendo la app…"
echo
echo "  → http://localhost:3000"
echo
echo "  Para cerrarla: Control + C en esta ventana."
echo "  Para abrirla otro día:  cd \"$ROOT\" && ./start.sh"
echo
( sleep 9; open "http://localhost:3000" >/dev/null 2>&1 ) &
exec ./start.sh
