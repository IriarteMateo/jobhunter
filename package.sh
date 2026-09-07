#!/usr/bin/env bash
# Arma una copia limpia del proyecto, lista para pasar a otra computadora.
#
# Excluye todo lo que es específico de esta máquina: el entorno virtual (tiene
# rutas absolutas), node_modules, la base de datos con tus postulaciones y los
# registros. En la otra computadora se regenera solo con ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

DESTINO="${1:-$HOME/Desktop/jobhunter-para-compartir}"
rm -rf "$DESTINO"
mkdir -p "$DESTINO"

echo "→ copiando el proyecto…"
rsync -a \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.db' --exclude '*.db-wal' --exclude '*.db-shm' \
  --exclude 'logs/' --exclude '*.log' --exclude '.daily.lock' \
  --exclude '.DS_Store' \
  --exclude 'next-env.d.ts' \
  --exclude '.env' --exclude '.env.local' \
  --exclude '.pipeline.lock' \
  ./ "$DESTINO/"

# Ningún .env viaja: pueden tener credenciales (IMAP, API keys, SMTP). rsync ya
# los excluyó por nombre en cualquier subdirectorio; acá va el ejemplo y, aparte,
# los dos flags de ingesta que no son secretos y que la app necesita prendidos.
cp .env.example "$DESTINO/.env"
cat > "$DESTINO/backend/.env" <<'FLAGS'
# Lectura de HTML público habilitada: sólo se usa en sitios cuyo robots.txt
# permite la ruta (verificado antes de cada request). Necesario para los
# career sites de SAP SuccessFactors (EY, SAP, Siemens).
ENABLE_HTML_SCRAPING=true
ENABLE_BROWSER_RENDERING=true
FLAGS

# Red de seguridad: si algún .env se coló igual, el paquete no sale.
if find "$DESTINO" -name '.env' ! -path "$DESTINO/.env" ! -path "$DESTINO/backend/.env" | grep -q .; then
  echo "ABORTADO: se coló un .env inesperado en el paquete." >&2; exit 1
fi
if grep -rIl -E '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|IMAP_PASSWORD|SMTP_PASSWORD|TELEGRAM_BOT_TOKEN)=.+' "$DESTINO" 2>/dev/null | grep -q .; then
  echo "ABORTADO: hay una credencial con valor dentro del paquete." >&2; exit 1
fi

chmod +x "$DESTINO"/*.sh "$DESTINO"/*.command 2>/dev/null || true

# --- DMG: UN SOLO archivo que macOS no expande solo ---------------------
# Un .zip lo abren automáticamente Mail, WhatsApp o el propio Finder, y del
# otro lado llegan cientos de archivos sueltos. Un disco de imagen viaja
# entero y se monta con doble clic.
DMG="${DESTINO}.dmg"
rm -f "$DMG"
# hdiutil copia el CONTENIDO de -srcfolder, no la carpeta: sin este paso
# intermedio el disco se monta con 110 archivos sueltos en la raíz.
STAGING=$(mktemp -d)
cp -R "$DESTINO" "$STAGING/Job Hunter"
if hdiutil create -quiet -volname "Job Hunter" -srcfolder "$STAGING" \
        -ov -format UDZO "$DMG" 2>/dev/null; then
  TAMANIO_DMG=$(du -h "$DMG" | cut -f1)
else
  DMG=""
fi
rm -rf "$STAGING"

ZIP="${DESTINO}.zip"
rm -f "$ZIP"
(cd "$(dirname "$DESTINO")" && zip -qr "$(basename "$ZIP")" "$(basename "$DESTINO")" -x '*.DS_Store')
TAMANIO=$(du -sh "$DESTINO" | cut -f1)
TAMANIO_ZIP=$(du -h "$ZIP" | cut -f1)

echo
echo "✓ Listo para enviar:"
[ -n "$DMG" ] && echo "    ★ DMG:    $DMG  ($TAMANIO_DMG)   ← mandá ESTE"
echo "      zip:    $ZIP  ($TAMANIO_ZIP)"
echo "      carpeta: $DESTINO  ($TAMANIO)"
echo
echo "  Mandá el .dmg: es un solo archivo y ninguna app lo desarma en el camino."
echo "  (Un .zip lo expanden Mail, WhatsApp y el Finder, y llegan cientos de sueltos.)"
echo
echo "  Del otro lado NO hace falta descomprimir ni doble clic."
echo "  Mandale el zip y esta ÚNICA línea para pegar en la Terminal:"
echo
echo "    Z=\$(ls -t ~/Downloads/jobhunter*.zip ~/Desktop/jobhunter*.zip 2>/dev/null|head -1); unzip -oq \"\$Z\" -d ~/Desktop && cd ~/Desktop/jobhunter-para-compartir && xattr -dr com.apple.quarantine . && ./INSTALAR.sh"
echo
echo "  Si es la PRIMERA vez -> ./INSTALAR.sh   (la línea de arriba ya lo llama)"
echo "  Si YA la tenía instalada -> ./ACTUALIZAR.sh  (conserva sus guardados)"
echo
echo "  Deja TODO igual que acá: dependencias, empleos ya cargados, la"
echo "  búsqueda diaria de las 07:30 y la app abierta en el navegador."
echo "  Tarda entre 5 y 10 minutos y no hay que tocar nada más."
echo
echo "  Instrucciones completas en SETUP.md, dentro de la carpeta."
