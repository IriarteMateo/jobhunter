# AI Job Hunter

Buscador, analizador y ranking diario de empleos para un **primer trabajo** en Buenos Aires.
No es un agregador: descarta agresivamente y explica por qué recomienda cada aviso.

En la última corrida real contra fuentes en vivo: **1704 avisos revisados → 37 relevantes → 3 recomendados, en 11 segundos.**

---

## Qué hace

Todos los días a las 07:30 (America/Argentina/Buenos_Aires):

```
FETCH SOURCES → PARSE → NORMALIZE → DEDUPE → SENIORITY → REQUIREMENTS
   → AI MATCHING → COMPANY SCORING → RANKING → DATABASE → NOTIFICATIONS
```

Y produce, por aviso, cuatro indicadores y una explicación accionable:

| Indicador | Qué responde |
|---|---|
| `fit_score` | ¿Qué tan recomendable es que **esta** candidata aplique a **este** puesto? |
| `company_quality_score` | ¿Qué tan buena es la empresa? (con `confidence` explícita) |
| `career_value_score` | Aunque no sea perfecto, ¿qué tan buen primer paso es? |
| `german_advantage_score` | ¿El alemán juega a favor acá? |
| `final_score` | 60% fit + 20% empresa + 15% carrera + 5% recencia, ± boosts y penalizaciones |

---

## Arranque rápido

```bash
./start.sh
```

Backend en `http://127.0.0.1:8080` (docs en `/docs`), frontend en `http://localhost:3000`.
La primera vez crea el venv, instala dependencias, arma la base SQLite y carga el perfil
y las 65 empresas objetivo.

### Paso a paso

```bash
cp .env.example .env

cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.seed                     # perfil + empresas + catálogo de fuentes
.venv/bin/python -m uvicorn app.main:app --port 8080
```

```bash
cd frontend
npm install
npm run dev
```

Después, en la app: **Buscar nuevos empleos ahora**.

### Con Docker (PostgreSQL incluido)

```bash
cp .env.example .env
docker compose up --build
```

---

### Si la app aparece sin estilos

Se ve el contenido pero con letra serif y links azules, como una página de 1998.
Significa que el servidor de producción de Next.js está sirviendo el índice de un build
anterior: pasa si se corre `npm run build` con `npm run start` levantado. La solución es
reconstruir y reiniciar:

```bash
cd frontend && rm -rf .next && npm run build && npm run start
```

`./start.sh` no tiene este problema: usa el modo desarrollo, que recompila solo, y además
libera los puertos 3000 y 8080 antes de arrancar.

## Instalarla en otra computadora

Cada persona tiene su propia instalación: su perfil, su base de datos, sus
postulaciones y su agente diario. No se comparte nada y no cuesta nada.

```bash
./package.sh          # arma una copia limpia (~1 MB) en el Escritorio
```

Se pasa por AirDrop o pendrive, y en la otra Mac: `./start.sh`. Paso a paso y
solución de problemas en **[SETUP.md](SETUP.md)**.

La copia excluye a propósito el entorno virtual (tiene rutas de esta máquina),
`node_modules`, la base de datos y el `.env` real —que puede tener credenciales—.
`start.sh` detecta un entorno virtual de otra computadora y lo rehace solo.

## Que corra solo todos los días

Hay dos schedulers y sirven para cosas distintas:

| | Dónde vive | Corre si la app está cerrada |
|---|---|---|
| APScheduler (incluido) | dentro del proceso de la app | ❌ no |
| **Agente de macOS (launchd)** | en el sistema operativo | ✅ sí |

El scheduler interno alcanza si dejás la app abierta todo el día. Para que la búsqueda
corra de verdad sin tocar nada:

```bash
./install-daily.sh
```

Queda a las 07:30 (`./install-daily.sh 9 15` para otra hora). Corre aunque la app esté
cerrada, y **launchd recupera las corridas perdidas**: si la Mac estaba dormida a esa hora,
la ejecuta apenas despierta.

```bash
launchctl start com.jobhunter.daily          # probar ahora
tail -f backend/logs/daily.log               # ver el registro
launchctl list | grep jobhunter              # estado y último código de salida
./uninstall-daily.sh                         # desinstalar
```

La corrida diaria usa `python -m app.daily`, que no necesita el servidor web: abre la base,
ejecuta el pipeline y sale. Un lock evita que dos corridas se pisen si la app también está
abierta, y se descarta solo si una corrida anterior murió a mitad de camino.

**El único límite es físico:** si la Mac está apagada, no corre nada — se ejecuta en el
próximo arranque. Dormida sí funciona. Para independencia total del equipo hay que
desplegar el backend en un servidor (Railway, Render y Fly.io tienen plan gratuito).

> **¿Vas a trabajar sobre el código con Claude Code?** Empezá por
> **[CLAUDE.md](CLAUDE.md)**: tiene el porqué de cada decisión y las trampas ya
> encontradas. Se lee solo al abrir la carpeta.

## Arquitectura

```
jobhunter/
├── backend/                     Python 3.12+ · FastAPI · SQLAlchemy 2.0
│   └── app/
│       ├── config.py            settings desde ENV (nada sensible en código)
│       ├── models.py            16 tablas, portable SQLite ↔ PostgreSQL
│       ├── data/                taxonomía de roles, geografía, empresas semilla
│       ├── sources/             19 adaptadores + registry + chequeo de robots.txt
│       ├── pipeline/            normalize · dedupe · experience · seniority ·
│       │                        languages · location · roles · skills ·
│       │                        prefilter · scoring · runner
│       ├── ai/                  proveedor desacoplado + prompts + validación
│       ├── services/            perfil · empresas · stats · notificaciones · CV · feedback
│       ├── api/routes/          24 endpoints REST
│       └── scheduler.py         APScheduler, corrida diaria
└── frontend/                    Next.js 14 · TypeScript · Tailwind
    └── src/app/                 Hoy · Top Picks · Empleos · Alemán ·
                                 Historial · Métricas · Perfil · Config
```

### Por qué el motor determinístico va primero

El pipeline es de **costo creciente** (§38). Los filtros baratos corren primero y el LLM
sólo ve lo que ya pasó el filtro determinístico y supera `AI_PREFILTER_THRESHOLD`. Los
análisis se cachean por hash de contenido: un aviso ya analizado no se reanaliza al día
siguiente.

**Sin ninguna API key el sistema funciona completo.** El motor de reglas hace matching,
scoring, explicación y ranking. El LLM es un refinamiento opcional, no un requisito.

### Qué cuesta operarlo

**Nada, en la configuración por defecto.** Todas las fuentes de empleo son APIs públicas
gratuitas y sin cuenta: son los mismos endpoints que consumen las páginas de carreras de las
propias empresas. La base SQLite, el scheduler y el motor de matching tampoco cuestan nada.

El único gasto posible es opcional: activar un LLM para refinar el análisis. Medido sobre los
avisos reales de esta app (~2.250 tokens de entrada + ~450 de salida por aviso) y analizando
~20 avisos por día:

| Modelo | Por aviso | Por mes |
|---|---|---|
| `claude-opus-5` (default) | USD 0,022 | ~USD 13,50 |
| `claude-sonnet-5` | USD 0,009 | ~USD 5,40 |
| `claude-haiku-4-5` | USD 0,005 | ~USD 2,70 |

En la práctica sale bastante menos: el prefiltro geográfico descarta el 94% de los avisos antes
de llegar al LLM, y el caché por hash de contenido evita reanalizar un aviso ya visto. Si el
volumen creciera, la Batch API de Anthropic corta ese costo a la mitad — la corrida diaria no
es sensible a la latencia.

---

## Decisiones de calidad que se validaron contra datos reales

Cada una salió de ver el sistema fallar con avisos de verdad:

| Problema encontrado | Corrección |
|---|---|
| `"intern"` matcheaba dentro de `"international"` y clasificaba puestos senior como pasantías | Matching con límites de palabra en toda la taxonomía |
| Avisos en Gurugram y Ámsterdam encabezaban el ranking | Compuerta geográfica **antes** de la ingesta; la ubicación declarada manda sobre el cuerpo |
| Un puesto en São Paulo pasaba por mencionar "LATAM" en la descripción | Si el aviso declara una ciudad concreta, esa ciudad decide |
| `"Analista de Mantenimiento"` matcheaba `"Analista de Datos"` | Se separan tokens genéricos (`analista`, `junior`) de tokens distintivos |
| `"medicina prepaga"` (un beneficio) se leía como requisito de título de médico | Bloqueos académicos como frases específicas, no palabras sueltas |
| `"Portuguese (not required)"` se leía como portugués requerido | Detección de negación antes de la marca positiva |
| Un puesto de psicólogo infantil llegaba a 57 por no tener señales en contra | Compuerta multiplicativa por compatibilidad de rol |
| `"2 años de cursada restantes"` se leía como 2 años de experiencia | Contexto académico excluido del parser de experiencia |
| Un esquema 100% comisión aparecía como elegible | Señales de informalidad ⇒ no elegible, no sólo penalizado |
| `"Analyst (Hybrid)"` quedaba con modalidad sin especificar | La modalidad también se lee del título |
| 20 tests de API fallaban en una instalación limpia: el fixture recargaba módulos y re-registraba las tablas de SQLAlchemy | La base de test se fija en `conftest.py` antes de importar la app |
| `bumeran.com.ar` no quedaba bloqueado para descarga por comparar con `endswith` | Comparación por etiquetas de dominio completas |
| Importar el link de una career page guardaba `"Jobs at EBANX"` como si fuera un puesto | Las URLs de ATS se resuelven por su API; guardia que rechaza páginas de listado |
| Workday descartaba 76 avisos argentinos por "sin ubicación": su listado no la trae | La ubicación, el país y la modalidad se leen del detalle de cada aviso |

---

## Cumplimiento y fuentes

El orden de preferencia del brief se respeta literalmente:

| Nivel | Fuentes | Estado |
|---|---|---|
| API oficial | Remotive, Arbeitnow, Jobicy, Himalayas | ✅ activas |
| API pública de ATS | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, **Workday**, **Oracle Recruiting Cloud**, **Eightfold** | ✅ activas |
| Casilla propia | **Alertas por email** de LinkedIn, Indeed, Bumeran, ZonaJobs y Glassdoor | ⚙️ `IMAP_ENABLED=true` (gratis) |
| HTML público | Career pages (JSON-LD `schema.org/JobPosting`), SAP SuccessFactors | ⚙️ `ENABLE_HTML_SCRAPING=true`, **verifica `robots.txt` antes de cada request** |
| Sitio restringido | Consulta directa a LinkedIn, Indeed, Bumeran, ZonaJobs, Glassdoor | ⛔ apagada por política del sitio |

**No se evade nada.** Sin CAPTCHAs, sin bypass de anti-bot, sin credenciales ajenas, sin
saltear rate limits. Los adaptadores de esos portales existen y quedan listos para conectar
una API oficial si algún día hay acuerdo de partner.

### Cómo entran igual los avisos de LinkedIn, Indeed y Bumeran

Sus sitios están cerrados al acceso automatizado, pero los datos no. Hay tres caminos, y
la app implementa los tres:

1. **Alertas por email (el principal).** Creás una alerta de búsqueda en cada portal; ellos
   te mandan las ofertas a tu casilla. La app se conecta por IMAP a *tu* correo, encuentra
   esos mails y extrae los avisos. Leer el correo propio no es scraping: es el canal que el
   portal eligió para entregarte esos datos. Se activa con `IMAP_ENABLED=true`.
   Una sola fuente destraba los cinco portales.
2. **Importar a mano.** *Empleos → Importar un aviso*: pegás el texto de cualquier aviso y
   pasa por el mismo motor de scoring. Si el link es de un ATS con API pública (Greenhouse,
   Lever, Ashby, SmartRecruiters), alcanza con pegar el link: se trae el aviso completo por
   su API en vez de raspar HTML.
3. **Búsquedas armadas.** *Config → Portales con restricciones* genera las URLs ya filtradas
   (entry level, orden por fecha, Buenos Aires) para abrirlas en el sitio original.

Limitación honesta del camino 1: el mail trae título, empresa, ubicación y link, pero **no
la descripción completa**. Esos avisos se marcan `needs_detail`, reciben menor confianza y
la tarjeta invita a abrir el link. Cuando el mismo puesto llega además por el ATS oficial de
la empresa, la deduplicación los fusiona y el `apply_url` queda apuntando a la página
oficial — la alerta funciona como canal de *descubrimiento* y el ATS aporta el detalle.

### Las empresas grandes no necesitan scraping

Casi ninguna multinacional usa Greenhouse o Lever: corren sobre Workday, Oracle Recruiting
Cloud, Eightfold o SuccessFactors. Todos exponen la **misma API JSON pública que consume su
propia página de carreras** — sin auth, sin scraping, y con mejores datos que raspar HTML.

Verificado en vivo con ofertas reales en Argentina:

| ATS | Empresas conectadas |
|---|---|
| Workday | Accenture, Salesforce, Mastercard, Unilever, Visa, PwC (+ board de Campus & Graduates), Santander, Coca-Cola |
| Greenhouse | EBANX, Clara, QuintoAndar, Cabify, Payoneer, Bitso, Adyen, Wellhub, Datadog |
| SmartRecruiters | Bosch, Kenvue, Danone, Nestlé, L'Oréal, Henkel |
| Oracle Recruiting Cloud | Oracle, ICBC Argentina |
| Eightfold | Boston Consulting Group |
| Ashby / Lever | Nubank / Kavak |

**30 de las 66 empresas objetivo tienen conector.** Para el resto —y para cualquier empresa
nueva— está el detector: *Config → Detectar el ATS de una empresa*. Pegás la URL del buscador
de empleos, la app reconoce la plataforma, arma la configuración del conector y **la prueba
contra la API real** antes de proponerla. Reconoce 10 plataformas con conector y avisa
explícitamente cuando encuentra una que todavía no lo tiene (Avature, Phenom, Taleo, iCIMS,
BrassRing) en vez de decir "desconocido".

---

## Agregar una fuente nueva

1. Creá la clase en `backend/app/sources/`:

```python
from app.sources.base import BaseJobSource, ComplianceLevel, RawJob, SourceKind, SourceTarget

class MiFuente(BaseJobSource):
    key = "mi_fuente"
    label = "Mi Fuente"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "Por qué esta fuente se puede consultar automáticamente."

    def default_targets(self) -> list[SourceTarget]:
        # Sólo para fuentes que no dependen de una empresa concreta
        return [SourceTarget("business", "Mi Fuente · business", {"cat": "business"})]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        data = await self._get_json("https://...", params=target.params)
        return [RawJob(source=self.key, source_job_id=str(j["id"]), url=j["url"],
                       title=j["title"], company=j["company"], location=j.get("location"),
                       description=j.get("description")) for j in data["jobs"]]

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw
```

2. Registrala en `backend/app/sources/registry.py` (`SOURCE_CLASSES`). Si los objetivos
   salen de las empresas objetivo, agregá su `key` a `COMPANY_DRIVEN`.
3. Agregá un test en `backend/tests/test_sources.py`.
4. Reiniciá: aparece sola en **Config → Estado de las fuentes**.

No hace falta tocar nada más. Una fuente que falla queda registrada en `source_logs` y
**no afecta al resto de la corrida** — hay un test que lo verifica.

Para conectar una empresa a un ATS existente no hace falta código: **Config → Empresas
objetivo**, elegí el ATS y pegá el token del board (por ejemplo `greenhouse` + `ebanx`).
Para Workday el campo `careers_url` usa el formato `tenant|site|host`
(ej. `santander|SantanderCareers|wd3`).

---

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

127 tests sobre deduplicación, normalización, parsing de experiencia, clasificación de
seniority, detección de alemán, score de ubicación, prefiltro, matching de roles,
extracción de skills, scoring de punta a punta, adaptadores de fuentes, parseo de mails
de alerta, importación manual, detección de ATS, corrida diaria del sistema y API. Los fixtures son avisos reales anonimizados en
`backend/tests/fixtures/` (avisos en `jobs.json`, mails en `emails/`).

---

## Endpoints principales

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/api/dashboard/today` | El bloque "HOY" |
| `GET` | `/api/jobs` | Listado con ~20 filtros |
| `GET` | `/api/jobs/top-picks` | Las 8 categorías destacadas |
| `POST` | `/api/jobs/{id}/status` | Guardar · Aplicar · Descartar · Entrevista |
| `POST` | `/api/jobs/import` | Importar un aviso por texto o link |
| `POST` | `/api/companies/detect` | Detectar y verificar el ATS de una empresa |
| `POST` | `/api/runs` | Buscar ahora |
| `POST` | `/api/runs/reanalyze` | Recalcular scores sin volver a consultar fuentes |
| `GET` | `/api/sources/health` | Panel de salud de fuentes |
| `GET` | `/api/sources/search-links` | Búsquedas armadas para portales restringidos |
| `PUT` | `/api/config/{key}` | Editar pesos y umbrales |
| `GET` | `/api/config/personalization` | Qué ajustes por feedback están activos |

Documentación interactiva completa en `http://127.0.0.1:8080/docs`.

---

## Deployment

| Componente | Destino sugerido |
|---|---|
| Frontend | Vercel — root `frontend/`, variable `BACKEND_URL` |
| Backend | Railway / Render / Fly.io — `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Base de datos | Supabase PostgreSQL — `DATABASE_URL=postgresql+psycopg://...` |
| Scheduler | Incluido (APScheduler) mientras el proceso viva. En local, `./install-daily.sh` lo saca a launchd; en un host que duerma el proceso, apagá `SCHEDULER_ENABLED` y llamá `POST /api/runs` desde un cron externo. |

El schema se crea solo al arrancar. Para producción con migraciones versionadas,
`alembic init` sobre `app.db.Base.metadata`.

---

## Notas de honestidad del sistema

- **No inventa datos.** El salario sólo se muestra si viene publicado. Si un dato no está
  en el aviso, es `Unknown`.
- **La calidad de empresa viene con `confidence`.** `HIGH`/`MEDIUM` cuando hay señales
  verificables; `LOW` cuando no, y la UI lo muestra como "info limitada".
- **Cuando no sabe el nivel, no promete.** Un aviso con seniority indeterminado no puede
  superar 79 puntos.
- **La personalización es visible.** Cada ajuste aprendido del feedback se muestra en
  Métricas con su motivo, y se puede apagar.
- **Toda respuesta del LLM se valida** antes de usarse; si falla, queda el análisis
  determinístico.
