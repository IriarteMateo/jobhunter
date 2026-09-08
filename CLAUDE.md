# CLAUDE.md — contexto del proyecto

Este archivo es para vos, Claude. Lo lee Claude Code al abrir la carpeta.
Contiene el porqué de las decisiones, no sólo el qué: varias cosas que parecen
mejorables ya se probaron y se revirtieron por una razón concreta.

---

## Qué es

**AI Job Hunter**: buscador, analizador y ranking diario de empleos para el
**primer trabajo** de una persona recién graduada en Buenos Aires.

No es un agregador. Su valor está en **descartar**: de ~2.500 avisos crudos
sobrevive el 1-3%. En la última corrida completa: `2520 crudos → 372 relevantes
→ 78 recomendados`, 68 objetivos consultados, 0 fallos, 110 segundos.

El perfil por defecto (editable en la UI): Licenciatura en **Negocios Digitales**,
Universidad de San Andrés, **sin experiencia laboral formal**, español nativo,
inglés y **alemán** avanzados, vive en **San Isidro** (Zona Norte).

---

## Arrancar y verificar

```bash
./ABRIR.command                             # todo en uno: instala si hace falta, busca y abre
./start.sh                                  # sólo levantar (para desarrollo)
cd backend && .venv/bin/python -m pytest    # 189 tests, deben pasar todos
```

Frontend en **http://localhost:3000** (con el puerto; `localhost` a secas es el 80 y no hay nada).

Corrida manual del pipeline sin levantar la web:

```bash
cd backend && .venv/bin/python -m app.daily
```

---

## Arquitectura

```
backend/app/
├── config.py         settings desde ENV (pydantic-settings). Nada sensible en código.
├── models.py         16 tablas. Portable SQLite ↔ PostgreSQL: JSON genérico, UTC naive.
├── daily.py          entrypoint del cron/launchd
├── data/             taxonomía de roles, geografía, 86 empresas semilla
├── sources/          23 adaptadores + registry + chequeo de robots.txt
├── pipeline/         normalize · dedupe · experience · seniority · languages ·
│                     location · roles · skills · prefilter · scoring · summarize ·
│                     runlock · runner
├── ai/               proveedor desacoplado (heuristic/anthropic/openai) + validación
├── services/         perfil · empresas · stats · notificaciones · CV · feedback ·
│                     importer · ats_detector · serialize
└── api/routes/       29 endpoints REST

frontend/src/app/     Hoy · Recientes · Top Picks · Empleos · Empresas · Alemán ·
                      Historial · Métricas · Perfil · Config
                      (Next.js 14, TypeScript, Tailwind)
```

**~11.800 líneas de Python, ~3.000 de TypeScript, 189 tests.**

### Las tres vistas de empleos

No se pisan, cada una responde otra pregunta:

- **`/recientes`** — "¿qué entró?" Feed cronológico agrupado por día, con chips de
  atajo (nuevos hoy, sin experiencia, con alemán, por familia de rol). Arranca
  con umbral 0 a propósito: muestra el panorama completo, no sólo lo recomendado.
- **`/empleos`** — "¿dónde aplico?" Filtros profundos, umbral 70 por defecto.
- **`/empresas`** — "¿qué hay en X?" Grid de las 56 empresas con conteos reales.
  Al tocar una, el detalle **reemplaza la grilla** (drill-down con botón "← Todas
  las empresas"). Al principio se renderizaba debajo de la grilla y el usuario
  reportó que "no se abre": los avisos quedaban en el píxel 7048, nueve pantallas
  abajo. `scrollIntoView` tampoco alcanzó — la solución es no tener que scrollear.

### Orden de las listas

`components/SortControl.tsx` es el único control de orden: lo usan Hoy, Recientes,
Top Picks, Empleos, Empresas, Alemán e Historial. Siete campos (puntaje final,
fit, empresa, carrera, alemán, publicación, descubrimiento) × dos direcciones.

Dos detalles que importan:

- La **etiqueta de dirección cambia según el campo**: "↓ Mejor primero" para un
  puntaje, "↓ Más reciente primero" para una fecha. "Mejor" no aplica a una fecha.
- **"Antigüedad del aviso" ordena por `COALESCE(publication_date, first_seen_date)`.**
  SuccessFactors no informa fecha de publicación en *ninguno* de sus avisos (EY:
  35 de 35 en nulo). Ordenar por la columna pelada dejaba la lista en el orden del
  desempate por puntaje, y el usuario veía "encontrado ayer" arriba de "hace 2 h".
  El respaldo es el mismo que ya usa la tarjeta al mostrar "Encontrado hace…" en
  vez de "Publicado hace…": el orden tiene que coincidir con lo que se ve.
  Por eso la etiqueta dice "Antigüedad" y no "Fecha de publicación".

En `/recientes`, agrupar por día sólo tiene sentido ordenando por fecha de
descubrimiento: con cualquier otro campo el agrupado se desactiva solo.

### El resumen del aviso

`pipeline/summarize.py` segmenta la descripción por sus encabezados y devuelve
**las frases que ya están escritas**: overview, qué harías, qué piden, deseables,
beneficios. No genera texto — sin LLM no hay forma honesta de redactar un
resumen propio, y el §53 prohíbe inventar. Hay un test
(`test_summary_never_invents_text`) que verifica que cada frase devuelta exista
literalmente en el aviso original.

Se calcula al vuelo en `services/serialize.py:to_detail()`, sin columna nueva:
así no hace falta migrar bases que ya existen.

### El pipeline

```
FETCH → PARSE → NORMALIZE → PREFILTER → DEDUPE → SENIORITY → REQUIREMENTS
  → SCORING → COMPANY SCORING → RANKING → DB → NOTIFICACIONES
```

El **prefiltro** (`pipeline/prefilter.py`) es lo que hace viable el sistema:
descarta ~94% antes de tocar la base, por geografía y nivel evidente. Sin él, la
base se llena de avisos de Gurugram y Ámsterdam.

---

## Reglas que NO hay que romper

Estas salieron del brief original y de errores reales. Si algo las contradice,
está mal aunque los tests pasen.

### 1. Cumplimiento de las fuentes

Orden de preferencia, implementado literalmente en `sources/base.py:ComplianceLevel`:

| Nivel | Qué es | Estado |
|---|---|---|
| `official_api` | API pública documentada | activas |
| `public_ats_api` | La misma API que consume la career page de la empresa | activas |
| `user_inbox` | Alertas por email que el portal manda a la casilla propia | opt-in |
| `public_html` | HTML público, **verificando robots.txt antes de cada request** | opt-in |
| `restricted` | LinkedIn, Indeed, Bumeran, ZonaJobs, Glassdoor | **apagadas** |

**Nunca**: evadir CAPTCHA, romper anti-bot, saltear rate limits, usar credenciales
ajenas. Google quedó afuera porque **su robots.txt prohíbe** `/about/careers/`, y
el conector se detiene solo — eso es correcto, no un bug a arreglar.

### 2. No inventar datos

- Salario: sólo si viene publicado (`salary_is_published`). Nunca estimado.
- Calidad de empresa: siempre con `confidence` (HIGH/MEDIUM/LOW). LOW se muestra
  como "info limitada" en la UI.
- Si el nivel del puesto no se puede determinar, el score se topea (74 en modo
  estricto). El sistema declara su incertidumbre en vez de esconderla.
- Toda respuesta del LLM se valida (`ai/base.py:validate_llm_payload`) antes de usarse.

### 3. El motor determinístico es el primario

Sin ninguna API key el sistema funciona **completo**: matching, scoring,
explicación y ranking. `AI_PROVIDER=heuristic` es el default y hace el 100% del
trabajo. El LLM es refinamiento opcional.

**No conviertas el LLM en dependencia obligatoria.** La usuaria eligió
explícitamente no pagar.

### 4. Foco en primer empleo

`pipeline/scoring.py:EXPERIENCE_POLICY` tiene tres modos, y el default es
`strict`: descarta Semi Senior en adelante y todo lo que pida 1+ año, **aunque
figure como "deseable"**. Es una decisión explícita de la usuaria, no un bug.
Se cambia desde Config, no tocando el código.

---

## Trampas conocidas (no reintroducir)

Cada una costó encontrarla con datos reales. Hay tests que las cubren.

| Trampa | Por qué |
|---|---|
| **Matching de substrings** | `"intern"` matchea dentro de `"international"`. Usar siempre `pipeline/text.py:has_term()` / `contains_any()`, que aplican límites de palabra. |
| **Cuerpo del aviso > ubicación declarada** | Un puesto en São Paulo que menciona "LATAM" NO es elegible. La ubicación declarada manda (`prefilter.py:geography_ok`). |
| **Tokens genéricos en títulos** | `"Analista de Mantenimiento"` matcheaba `"Analista de Datos"`. `roles.py:GENERIC_TOKENS` separa palabras distintivas de las que aparecen en cualquier título. |
| **Bloqueos académicos amplios** | `"medicina"` a secas matchea `"medicina prepaga"` (un beneficio). Los bloqueos deben ser frases específicas. |
| **Negaciones** | `"Portuguese (not required)"` se leía como requerido. `languages.py:NEGATED_REQUIREMENT` se evalúa **antes** que la marca positiva. |
| **Piso alto del fit** | Con dimensiones neutras, un puesto de psicólogo llegaba a 57. `scoring.py` aplica una **compuerta multiplicativa por rol** (`ROLE_GATE_FLOOR`). |
| **Workday no trae ubicación en el listado** | Sólo aparece en el detalle de cada aviso. Sin eso se descartaban 76 avisos argentinos por "sin ubicación". |
| **Fixtures que recargan módulos** | `importlib.reload` re-registra las tablas de SQLAlchemy y rompe según el orden de colección. La base de test se fija en `conftest.py` **antes** de importar la app. |
| **Párrafos cortados en varias líneas** | El overview quedaba a la mitad. Se unen cuando la línea previa no cierra oración y la siguiente arranca en minúscula. |
| **Bullets de 2 palabras** | `"Inglés intermedio"` se descartaba por corto. Dentro de una sección son requisitos válidos; el filtro de longitud sólo aplica fuera de sección. |
| **Detalle debajo de una grilla larga** | Si el detalle se renderiza al final de una lista de 56 tarjetas, hacer clic "no hace nada" a los ojos del usuario. Drill-down que reemplaza la vista, no un panel al pie. |
| **Dos corridas del pipeline a la vez** | Hay tres entradas —botón de la app, launchd, cron externo— y las tres escriben la misma base. Solapadas dan "database is locked" y un 500. `pipeline/runlock.py` es un lock **de archivo** (tiene que cruzar procesos, no basta una variable); el endpoint responde **409**, no 500: no es un error, está trabajando. |
| **Servidor levantado desde otra copia del proyecto** | Una copia de `package.sh` en el Escritorio es un proyecto completo: si se arranca desde ahí, sirve su propia base vacía y la app se ve *perdida* — 0 empleos, 0 empresas— con los datos reales intactos en otro lado. `/api/health` y `/api/config` devuelven `database` y `project_dir`, y Config los muestra: se diagnostica de un vistazo. |
| **Marcadores de experiencia comparados por substring** | `experience.py` usaba `any(m in text for m in MARKERS)`. El marcador `"0 years"` matcheaba dentro de `"more than 160 years of history"` (la reseña corporativa de BBVA) y un puesto que pedía **2 años** quedaba como "no requiere experiencia" y aparecía recomendado. Es la misma trampa que `"intern"` dentro de `"international"`: **siempre** `contains_any()` de `pipeline/text.py`, nunca `in`. |
| **Tarjetas que no distinguen elegible de no elegible** | Empresas, Empleos e Historial muestran avisos que no pasan el filtro, a propósito. Si `JobCard` los dibuja igual que a los recomendados —mismo botón verde "Aplicar", sin motivo— un puesto que pide 4 años parece aplicable, y el usuario concluye que el buscador está roto cuando en realidad acertó. La tarjeta lee `analysis.eligible` y muestra `not_eligible_reason`. |
| **Esperar la corrida dentro del POST** | Una búsqueda completa consulta 74 objetivos y tarda ~2 minutos. Si `POST /api/runs` la esperaba, el proxy de Next.js cortaba por timeout y el navegador mostraba **500 Internal Server Error** aunque el pipeline terminara perfecto. El endpoint dispara `asyncio.create_task` y responde al instante con `{run_id, status:"running"}`; la pantalla sigue el avance con `GET /api/runs/{id}`. |
| **`GET /api/runs/{id}` no tiene la misma forma que el POST** | El detalle por fuente y los motivos de descarte vienen **anidados en `stats`**, no en la raíz. Al hacer polling hay que aplanar (`{...estado, ...estado.stats}`) o `run.sources.filter(...)` explota y tira la página entera con "Application error". En `types.ts` esos campos son opcionales a propósito. |
| **Contadores que sólo se escriben al final** | Sin avance intermedio el botón parece colgado dos minutos. `_fetch_all` recibe un callback `on_progress` que va guardando `sources_queried`/`raw_jobs` en la fila del run a medida que cada fuente termina. Escribe en su **propia sesión** y traga excepciones: el avance es cosmético y nunca debe tumbar la corrida. |
| **Tests que tocan el lock real** | `LOCK_FILE` vive en el directorio del proyecto y lo comparte la app en marcha: correr la suite con la app abierta daba 409. `conftest.py` lo redirige a un temporal para toda la sesión. |
| **Guardias de auto-update que bloquean para siempre** | `auto-update.sh` no actualiza si hay cambios locales, para no pisarlos. Con `git status --porcelain` a secas eso incluye los **archivos sin seguimiento**: un `.DS_Store` o una captura guardada dentro de la carpeta habrían cortado las mejoras para siempre y en silencio. Va `--untracked-files=no`. Y la red de seguridad es que corre los tests después del merge: si fallan, `git reset --hard` al commit anterior, así un push roto nunca llega a la otra máquina. |
| **Rebuild con el server prendido** | Next.js en producción sirve un índice viejo → página sin estilos. `start.sh` usa modo dev a propósito. |

---

## Agregar una empresa

**No hace falta código.** Config → *Detectar el ATS de una empresa*: se pega la
URL del **buscador de empleos** (no la portada), el detector reconoce la
plataforma, arma la configuración y **la prueba contra la API real** antes de
proponerla. Si la página arma el listado con JavaScript, reintenta con navegador.

Formatos de `careers_url` según el ATS (ver `sources/registry.py:build_plan`):

| ATS | `ats_token` | `careers_url` |
|---|---|---|
| greenhouse / lever / ashby / smartrecruiters | token del board | — |
| phenom | — | host de carreras (`jobs.aon.com`, `www.pepsicojobs.com`) |
| workday | tenant | `tenant\|site\|host` → `accenture\|AccentureCareers\|wd103` |
| oracle_recruiting | — | `https://host\|SITE` → `https://jpmc.fa.oraclecloud.com\|CX_1001` |
| eightfold | token | dominio (`bcg.com`) **o** URL propia (`https://careers-meli.mercadolibre.com`) |
| successfactors | — | base del career site (`https://careers.ey.com/ey`) |

**Buscar por plataforma, no por empresa.** Cuando el detector devuelve varias veces
la misma plataforma "sin conector", ahí está el mayor retorno: construir ese
adaptador destraba todas juntas. Así apareció **Phenom** (`/api/jobs` en el propio
dominio de carreras) — Aon, PepsiCo, Schneider Electric y AXA de una sola vez.
Las que siguen repitiéndose sin conector son **Avature** (Nike, Deloitte) e
**iCIMS** (Booking).

**Dato del mercado local:** de 242 tokens probados en ATS globales, sólo 4
funcionaron para Argentina. Las empresas argentinas (Ualá, Galicia, Globant,
Tiendanube, Arcor) publican en Bumeran/ZonaJobs/LinkedIn o en portal propio.
Para cubrirlas, el camino es **activar las alertas por email** (`IMAP_ENABLED`),
no seguir adivinando tokens.

## Agregar una fuente nueva

1. Subclase de `BaseJobSource` en `sources/`, implementando `search_jobs()` y
   `normalize_job()`, con `compliance` y `compliance_note` explícitos.
2. Registrar en `sources/registry.py:SOURCE_CLASSES`. Si los objetivos salen de
   las empresas objetivo, sumar la key a `COMPANY_DRIVEN`.
3. Test en `tests/test_sources.py`.

Una fuente que falla queda en `source_logs` y **no afecta al resto** — hay un
test que lo verifica (`test_a_failing_source_does_not_raise`).

---

## Convenciones

- **Comentarios y textos de UI en español rioplatense.** Los comentarios explican
  el *porqué*, no el *qué*.
- Nombres de código en inglés, contenido para la usuaria en español.
- Los tests documentan intención: nombres largos y descriptivos, con docstring
  cuando el caso no es obvio.
- Fixtures de avisos reales anonimizados en `backend/tests/fixtures/`.

---

## Estado actual

- **86 empresas** en la lista, **56 con conector activo**
- **23 fuentes**, 68 objetivos por corrida
- Corrida diaria a las **07:30** vía launchd (`./install-daily.sh`), funciona con
  la app cerrada
- Notificación nativa de macOS cuando aparecen oportunidades nuevas
- Costo operativo: **cero**

## Cosas pendientes / ideas

- **Multiusuario**: la base ya tiene `user_id` en todas las tablas, pero la API
  asume un solo usuario (`services/profile.py:get_user` devuelve el primero).
  Hoy cada persona usa su propia instalación.
- **Deloitte, McKinsey, Disney**: identificados (Avature / timeout / Radancy) pero
  sin conector funcional. Sus listados no devuelven resultados para Buenos Aires.
- **Personalización por feedback**: `services/feedback.py` ya acumula señales y
  ajusta puntajes por familia de rol. Se muestra en Métricas y se puede apagar.
  Está deliberadamente simple y transparente, no es un modelo entrenado.
- **Alembic**: hoy el schema se crea con `create_all`. Para producción con
  migraciones versionadas, `alembic init` sobre `app.db.Base.metadata`.
