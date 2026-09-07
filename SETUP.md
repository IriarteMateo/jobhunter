# Instalar en otra computadora

La app está pensada para que cada persona tenga la suya: **su propio perfil, su
base de datos, sus postulaciones y su agente diario**. No se comparte nada entre
instalaciones, y no cuesta nada tener varias.

---

## Lo que hace falta (macOS)

| | Versión | Cómo verificar |
|---|---|---|
| Python | 3.12 o superior | `python3 --version` |
| Node.js | 20 o superior | `node --version` |

Si falta alguno, la forma más simple es instalarlos desde
[python.org](https://www.python.org/downloads/) y [nodejs.org](https://nodejs.org/).
Si ya tenés Homebrew: `brew install python node`.

---

## Pasos

**1. En la computadora que ya tiene la app**, generá la copia limpia:

```bash
cd ~/Desktop/bot/jobhunter && ./package.sh
```

Queda una carpeta en el Escritorio (`jobhunter-para-compartir`) de pocos MB, sin
el entorno virtual ni la base de datos. Pasala por AirDrop, pendrive o Drive.

**2. En la computadora nueva** no hace falta ni descomprimir a mano. Abrí la app
**Terminal** (Command + Espacio → "Terminal") y pegá esta única línea:

```bash
Z=$(ls -t ~/Downloads/jobhunter*.zip ~/Desktop/jobhunter*.zip 2>/dev/null|head -1); unzip -oq "$Z" -d ~/Desktop && cd ~/Desktop/jobhunter-para-compartir && xattr -dr com.apple.quarantine . && ./start.sh
```

Encuentra el zip esté donde esté (Descargas o Escritorio), lo descomprime, saca
el bloqueo de macOS e instala. Un solo paso.

> **¿Por qué no doble clic?**
> macOS bloquea los instaladores que llegan por WhatsApp o mail y avisa que están
> *"dañados"*. **No lo están**: es Gatekeeper, que desconfía de los scripts sin
> firma digital descargados de internet. Desde la Terminal no hay bloqueo, y el
> `xattr` de la línea es justamente lo que saca esa marca.
>
> Una vez hecho eso, `INSTALAR.command` sí funciona con doble clic para las
> próximas veces.

La primera vez tarda unos minutos: crea el entorno de Python, instala las
dependencias del frontend y arma la base. Después arranca solo en segundos.

Cuando termine, abrí **http://localhost:3000**

**3. Que corra sola todos los días:**

```bash
./install-daily.sh
```

Queda programada a las 07:30. Corre aunque la app esté cerrada, y avisa con una
notificación de macOS cuando encuentra oportunidades nuevas.

---

## Seguir trabajando sobre la app con Claude

En la raíz hay un **`CLAUDE.md`**. Claude Code lo lee solo al abrir la carpeta:
le explica la arquitectura, las decisiones tomadas y —sobre todo— las trampas ya
encontradas, para que no reintroduzca bugs que costó descubrir.

```bash
cd ~/Desktop/jobhunter && claude
```

Ideas de por dónde seguir están al final de ese mismo archivo.

## Ajustar el perfil

El perfil viene cargado con el de la candidata original. En **Perfil** se edita
todo: carrera, universidad, idiomas, skills, ubicaciones preferidas y áreas de
interés. Al guardar, la app recalcula todos los puntajes con los datos nuevos.

También se puede subir el CV en PDF: extrae una propuesta de datos que después
se revisa a mano antes de aplicar.

---

## Si algo falla

**"command not found: python3" o "node"** — falta instalar Python o Node (arriba).

**El entorno virtual quedó de la otra computadora** — `start.sh` lo detecta y lo
rehace solo. Si querés forzarlo:

```bash
rm -rf backend/.venv && ./start.sh
```

**La página aparece sin estilos** — se reconstruyó el frontend con el servidor
prendido. Solución:

```bash
cd frontend && rm -rf .next && npm run build && cd .. && ./start.sh
```

**Puerto ocupado** — `start.sh` libera los puertos 3000 y 8080 antes de arrancar,
así que no debería pasar. Si pasa, cerrá la Terminal vieja y volvé a correrlo.

**"Permission denied" al hacer doble clic** — el archivo perdió el permiso de
ejecución en la transferencia. Desde la Terminal, dentro de la carpeta:

```bash
chmod +x *.command *.sh && ./start.sh
```

**La página aparece en blanco** — fijate que la dirección tenga el puerto:
`http://localhost:3000`, no `localhost` a secas.

---

## Lo que NO se copia (a propósito)

- **La base de datos.** Cada persona arranca limpia, con sus propios empleos
  guardados, aplicados y descartados.
- **El archivo `.env` real.** Puede tener credenciales (la casilla de correo para
  las alertas, una API key). Se copia el `.env.example` en su lugar.
- **El entorno virtual y `node_modules`.** Tienen rutas de la otra máquina; se
  regeneran solos.

---

## ¿Y una sola instalación compartida?

Se podría subir a un servidor (Railway, Render y Fly.io tienen plan gratuito) y
entrar desde cualquier lado. Pero hoy la app maneja **un perfil por instalación**:
dos personas con carreras e intereses distintos verían recomendaciones mezcladas.
La base ya está preparada para varios usuarios, pero la API todavía asume uno.

Para dos personas, dos instalaciones es más simple y funciona mejor.
