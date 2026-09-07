#!/usr/bin/env bash
# Doble clic para instalar y abrir Job Hunter.
cd "$(dirname "$0")"
clear
cat <<'BANNER'

   ╭──────────────────────────────────────────╮
   │           A I   J O B   H U N T E R      │
   ╰──────────────────────────────────────────╯

BANNER

faltan=()
command -v python3 >/dev/null 2>&1 || faltan+=("Python 3.12+  →  https://www.python.org/downloads/")
command -v node    >/dev/null 2>&1 || faltan+=("Node.js 20+   →  https://nodejs.org/")
if [ ${#faltan[@]} -gt 0 ]; then
  echo "  Antes de seguir hay que instalar:"
  echo
  printf '     · %s\n' "${faltan[@]}"
  echo
  echo "  Instalalos, cerrá esta ventana y volvé a hacer doble clic acá."
  echo
  read -r -p "  (Enter para cerrar) " _
  exit 1
fi

echo "  La primera vez tarda unos minutos. Después arranca en segundos."
echo "  Cuando aparezca 'Ready', abrí:  http://localhost:3000"
echo
echo "  Para cerrar la app: Ctrl + C en esta ventana."
echo
sleep 2

chmod +x start.sh install-daily.sh uninstall-daily.sh package.sh 2>/dev/null || true
./start.sh
