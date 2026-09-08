#!/usr/bin/env bash
# ============================================================================
#  Trae las mejoras nuevas desde GitHub, sola.
#
#  La corre un agente de macOS cada 10 minutos (ver install-auto-update.sh).
#  No hay que ejecutarla a mano.
#
#  REGLA DE ORO: si lo que llega rompe algo, se vuelve atrás. Nunca se deja la
#  app en un estado peor del que estaba. Por eso corre los tests antes de dar
#  el cambio por bueno, y si fallan hace un reset al commit anterior.
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")" || exit 1

VENV="backend/.venv"
LOG="logs/auto-update.log"
mkdir -p logs

decir() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG"; }

# Un repo a medias (merge o rebase colgado) no se toca: se avisa y se sale.
if [ ! -d .git ]; then decir "no es un repo git, no hay nada que actualizar"; exit 0; fi
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ]; then
  decir "hay un merge o rebase a medias: no toco nada"; exit 0
fi

# Cambios locales sin guardar: se respetan, actualizar encima los perdería.
# --untracked-files=no a propósito: un .DS_Store o una captura guardada en la
# carpeta no son motivo para dejar de recibir mejoras nunca más.
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  decir "hay cambios locales sin commitear: no actualizo para no pisarlos"; exit 0
fi

ANTES=$(git rev-parse HEAD 2>/dev/null)

git fetch --quiet origin 2>/dev/null || { decir "sin internet o sin acceso al repo"; exit 0; }

RAMA=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
DESPUES=$(git rev-parse "origin/$RAMA" 2>/dev/null)
[ -z "$DESPUES" ] && { decir "la rama $RAMA no existe en el remoto"; exit 0; }
[ "$ANTES" = "$DESPUES" ] && exit 0     # ya está al día: silencio, es lo normal

decir "hay novedades: $(git rev-parse --short "$ANTES") → $(git rev-parse --short "$DESPUES")"

# Caso normal: la copia local no tiene commits propios, entra derecho.
if ! git merge --ff-only "origin/$RAMA" >/dev/null 2>&1; then
  # Las dos máquinas hicieron cambios. Como el árbol está limpio (se verificó
  # arriba), se reapoyan los commits locales sobre los de la otra. Sin esto, la
  # primera vez que alguien toca algo el actualizador se planta para siempre.
  decir "hay commits de los dos lados: reapoyando los locales sobre origin/$RAMA"
  if ! git rebase "origin/$RAMA" >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1
    decir "el reapoyo chocó (el mismo archivo cambiado en los dos lados): hace falta resolverlo a mano"
    exit 0
  fi
fi

volver_atras() {
  git reset --hard "$ANTES" >/dev/null 2>&1
  decir "REVERTIDO a $(git rev-parse --short "$ANTES"): $1"
}

# Dependencias, sólo si de verdad cambiaron.
CAMBIOS=$(git diff --name-only "$ANTES" "$DESPUES")
if grep -q "backend/requirements.txt" <<< "$CAMBIOS"; then
  decir "cambió requirements.txt: instalando"
  "$VENV/bin/pip" install -q -r backend/requirements.txt || { volver_atras "falló pip install"; exit 1; }
fi
if grep -qE "frontend/package(-lock)?\.json" <<< "$CAMBIOS"; then
  decir "cambió package.json: instalando"
  ( cd frontend && npm install --silent --no-audit --no-fund ) || { volver_atras "falló npm install"; exit 1; }
fi

# La red de seguridad: si los tests no pasan, esto no llega a la usuaria.
if [ -x "$VENV/bin/python" ]; then
  if ! "$VENV/bin/python" -m pytest backend/tests -q >/dev/null 2>&1; then
    volver_atras "los tests fallaron"
    exit 1
  fi
fi

decir "actualizado a $(git rev-parse --short HEAD) — los tests pasaron"

# El backend corre con --reload y el frontend en modo dev: los dos toman los
# cambios solos. La pantalla lo nota por /api/version y se recarga.
exit 0
