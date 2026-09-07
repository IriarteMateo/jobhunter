"""Taxonomía de roles, seniority, idiomas y señales de exclusión.

Todo lo que el motor determinístico usa para entender un aviso vive acá, para
poder ajustarlo sin tocar la lógica.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Familias de rol objetivo (§3 del brief)
# --------------------------------------------------------------------------- #
ROLE_FAMILIES: dict[str, dict] = {
    "product": {
        "label": "Product",
        "icon": "💻",
        "titles": [
            "product analyst", "product associate", "associate product manager",
            "junior product manager", "product operations", "product ops",
            "product strategy", "product specialist", "product owner junior",
            "analista de producto", "product manager trainee",
        ],
        "keywords": [
            "roadmap", "product discovery", "backlog", "user stories", "producto digital",
            "product metrics", "a/b test", "product lifecycle",
        ],
    },
    "business": {
        "label": "Business & Strategy",
        "icon": "📊",
        "titles": [
            "business analyst", "junior business analyst", "business operations analyst",
            "business development analyst", "strategy analyst", "commercial analyst",
            "planning analyst", "corporate strategy analyst", "analista de negocios",
            "analista comercial", "analista de planeamiento", "business intelligence analyst",
            "strategy & operations", "strategy and operations",
        ],
        "keywords": [
            "business case", "kpi", "stakeholders", "market analysis", "análisis de negocio",
            "reporting", "forecast", "estrategia comercial",
        ],
    },
    "consulting": {
        "label": "Consulting",
        "icon": "🧭",
        "titles": [
            "junior consultant", "business consultant", "strategy consultant",
            "associate consultant", "technology consultant", "analyst consultant",
            "digital transformation consultant", "consultor junior", "consultora junior",
            "management consultant", "associate analyst",
        ],
        "keywords": ["client engagement", "deliverables", "workstream", "consultoría"],
    },
    "data": {
        "label": "Data & Analytics",
        "icon": "📈",
        "titles": [
            "data analyst", "junior data analyst", "business intelligence analyst",
            "bi analyst", "analytics analyst", "digital analytics", "customer insights analyst",
            "marketing analytics", "analista de datos", "analista bi", "insights analyst",
            "reporting analyst",
        ],
        "keywords": ["sql", "power bi", "tableau", "looker", "dashboards", "data visualization"],
    },
    "marketing": {
        "label": "Marketing & Growth",
        "icon": "🚀",
        "titles": [
            "growth analyst", "growth marketing", "digital marketing analyst",
            "performance marketing", "marketing analyst", "crm analyst",
            "customer acquisition", "marketing intelligence", "analista de marketing",
            "growth associate", "marketing trainee",
        ],
        "keywords": ["seo", "sem", "paid media", "campaigns", "funnel", "retención", "ltv", "cac"],
    },
    "operations": {
        "label": "Operations",
        "icon": "⚙️",
        "titles": [
            "operations analyst", "business operations", "strategy & operations",
            "process analyst", "process improvement", "project analyst", "pmo analyst",
            "junior project manager", "analista de operaciones", "analista de procesos",
            "operations associate", "supply chain analyst",
        ],
        "keywords": ["procesos", "eficiencia", "sla", "workflow", "mejora continua", "pmo"],
    },
    "finance": {
        "label": "Finance & Fintech",
        "icon": "💰",
        "titles": [
            "financial analyst", "junior financial analyst", "fintech analyst",
            "payments analyst", "business finance analyst", "corporate finance",
            "fp&a analyst", "fp&a junior", "analista financiero", "analista de finanzas",
            "treasury analyst", "risk analyst junior",
        ],
        "keywords": ["p&l", "budget", "forecast", "presupuesto", "conciliación", "payments"],
    },
    "customer": {
        "label": "Customer & Experience",
        "icon": "🤝",
        "titles": [
            "customer experience analyst", "cx analyst", "customer success analyst",
            "customer strategy", "user experience research", "customer insights",
            "analista de experiencia", "customer success associate", "client services analyst",
        ],
        "keywords": ["nps", "customer journey", "churn", "satisfacción del cliente", "voc"],
    },
    "tech_business": {
        "label": "Technology Business",
        "icon": "🔧",
        "titles": [
            "technology analyst", "digital transformation analyst", "it business analyst",
            "technology consulting", "implementation analyst", "functional analyst",
            "analista funcional", "solutions analyst", "systems analyst junior",
            "technical account", "sap analyst",
        ],
        "keywords": ["requerimientos funcionales", "erp", "crm", "implementación", "sap"],
    },
}

# Señales de programa para graduados / primer empleo (§2)
GRADUATE_PROGRAM_TERMS = [
    "graduate program", "graduate programme", "graduate scheme", "trainee program",
    "programa de trainees", "jóvenes profesionales", "jovenes profesionales",
    "young professionals", "young talent", "early careers", "early career",
    "campus hire", "new grad", "new graduate", "leadership development program",
    "management trainee", "programa de desarrollo", "semillero", "primer empleo",
]

INTERNSHIP_TERMS = [
    "internship", "intern", "pasantía", "pasantia", "pasante", "praktikum",
    "practicante", "prácticas profesionales", "co-op", "werkstudent",
]

ENTRY_TERMS = [
    "entry level", "entry-level", "junior", "jr.", "jr ", "trainee", "graduate",
    "recién graduado", "recien graduado", "recently graduated", "recent graduate",
    "sin experiencia", "no experience", "first job", "primer empleo", "analista junior",
    "associate", "assistant", "aprendiz", "einsteiger", "berufseinsteiger",
]

# "Experienced Associate" es explícitamente lo contrario de un primer empleo,
# aunque el título diga "Associate".
EXPERIENCED_TITLE_TERMS = [
    "experienced", "experimentado", "experimentada", "con experiencia",
    "seasoned", "erfahren", "erfahrene", "advanced level", "nivel avanzado",
]

# Títulos que implican recorrido previo sin llegar a ser jefatura formal.
SEMI_SENIOR_TITLE_TERMS = [
    "managing consultant", "management consultant", "consultor de gestion",
    "specialist ii", "analyst ii", "associate ii", "level ii", "sr associate",
    "senior associate", "advisor", "asesor", "asesora",
    # En software corporativo el Account Executive es el nivel por encima del
    # BDR/SDR: lleva cuota y exige trayectoria comercial previa.
    "account executive", "ejecutivo de cuentas", "key account",
    "client partner", "relationship manager",
]

# Señales que descalifican por seniority (§21 false positives)
SENIOR_TERMS = [
    "senior", "sr.", "sr ", "ssr", "semi senior", "semisenior", "lead ", "team lead",
    "leader", "lider", "líder", "encargado", "encargada", "managing",
    "tech lead", "staff ", "principal ", "head of", "manager", "director", "vp ",
    "vice president", "chief ", "gerente", "jefe de", "responsable de", "supervisor",
    "coordinador", "coordinadora", "especialista senior", "expert", "architect",
]
# Términos que parecen senior pero no lo son en contexto junior
SENIOR_FALSE_FRIENDS = [
    "associate product manager", "junior project manager", "manager trainee",
    "management trainee", "assistant manager trainee", "product manager trainee",
    "account manager junior", "junior manager",
]

# Roles fuera de alcance (§3: evitar programación pura / DS avanzado)
TECHNICAL_HEAVY_TERMS = [
    "software engineer", "backend engineer", "frontend engineer", "full stack engineer",
    "fullstack developer", "desarrollador", "developer", "programador", "data engineer",
    "machine learning engineer", "ml engineer", "devops", "sre", "site reliability",
    "qa engineer", "mobile engineer", "android developer", "ios developer",
    "data scientist", "research scientist", "security engineer", "cloud engineer",
    "platform engineer", "systems engineer",
    # Español / portugués: los boards de LATAM publican en idioma local
    "ingeniero de software", "ingeniera de software", "engenheiro de software",
    "engenheira de software", "desenvolvedor", "desenvolvedora", "programador",
    "programadora", "analista de sistemas", "arquitecto de software",
    "cientista de dados", "engenheiro de dados", "ingeniero de datos",
    # Administración de sistemas / infraestructura: tampoco es Negocios Digitales
    "dba", "administrador de base", "base de datos", "database administrator",
    "presales", "preventas", "solutions architect",
    "sap basis", "administrador sap", "administrador de sistemas", "sysadmin",
    "network operations", "svcs operations", "infraestructura", "networking engineer",
    "soporte tecnico", "technical support", "help desk", "mesa de ayuda",
    "cybersecurity", "ciberseguridad", "seguridad informatica",
]

# Roles claramente incompatibles con el perfil
EXCLUDED_ROLE_TERMS = [
    "contador publico", "contador público", "contador ", "contadora", "cpa required",
    "matrícula profesional", "matricula profesional",
    "abogado", "lawyer", "attorney", "médico", "enfermer", "nurse", "chef",
    "cajero", "repositor", "vendedor de salón", "telemarketer", "call center agent",
    "operario", "chofer", "conductor", "seguridad física", "limpieza",
    "electricista", "mecánico", "soldador", "recepcionista",
]

# Señales de aviso de baja calidad (§17 penalizaciones)
LOW_QUALITY_SIGNALS = [
    "100% comisión", "100% comision", "solo comisión", "solo comision",
    "commission only", "sin sueldo básico", "sin sueldo basico",
    "monotributo obligatorio y sin relación de dependencia",
    "invertí en tu propio negocio", "emprendedor independiente",
    "trabajá desde casa ganando", "ingresos ilimitados", "networking multinivel",
    "multinivel", "mlm", "reclutamiento de vendedores", "pago por reclutar",
]

# --------------------------------------------------------------------------- #
# Idiomas
# --------------------------------------------------------------------------- #
GERMAN_TERMS = [
    "german", "german speaker", "german speaking", "german-speaking", "deutsch",
    "deutschsprachig", "german language", "advanced german", "bilingual german",
    "native german", "german market", "alemán", "aleman", "idioma alemán",
    "dach", "dach region", "germany", "austria", "switzerland", "deutschland",
]
GERMAN_REQUIRED_MARKERS = [
    "german is required", "german required", "fluent german", "native german",
    "must speak german", "verhandlungssicher", "muttersprache", "alemán excluyente",
    "aleman excluyente", "alemán obligatorio", "requires german", "german: required",
    "fließend deutsch", "fliessend deutsch", "sehr gute deutschkenntnisse",
]
GERMAN_VALUED_MARKERS = [
    "german is a plus", "german a plus", "german is an advantage", "german advantage",
    "knowledge of german", "german skills", "alemán valorado", "aleman valorado",
    "alemán es un plus", "deutschkenntnisse", "german is valued", "german proficiency",
]
GERMAN_DESIRABLE_MARKERS = [
    "german desirable", "german preferred", "german nice to have", "alemán deseable",
    "aleman deseable", "alemán no excluyente", "german optional", "german would be nice",
]

ENGLISH_TERMS = [
    "english", "inglés", "ingles", "english proficiency", "fluent english",
    "advanced english", "bilingual english", "english speaker",
]
SPANISH_TERMS = ["spanish", "español", "espanol", "castellano"]
PORTUGUESE_TERMS = ["portuguese", "português", "portugues", "brazilian portuguese"]

OTHER_LANGUAGE_TERMS = {
    "french": ["french", "francés", "frances", "français"],
    "italian": ["italian", "italiano"],
    "mandarin": ["mandarin", "chinese", "chino"],
}

# --------------------------------------------------------------------------- #
# Educación
# --------------------------------------------------------------------------- #
EDUCATION_BUSINESS_TERMS = [
    "business administration", "administración de empresas", "administracion de empresas",
    "economics", "economía", "economia", "negocios", "business", "marketing",
    "ingeniería industrial", "ingenieria industrial", "industrial engineering",
    "finance", "finanzas", "comercio", "comercialización", "international business",
    "negocios digitales", "digital business", "sistemas de información",
    "information systems", "management", "relaciones internacionales",
    "communications", "publicidad", "ciencias empresariales", "wirtschaft",
    "betriebswirtschaft", "licenciatura", "carreras afines", "afines",
    "estudiante universitario", "universitario", "bachelor", "degree",
]
# Bloqueos académicos reales. Deben ser frases específicas: "medicina" a secas
# matchea "medicina prepaga" (un beneficio, no un requisito de título).
EDUCATION_HARD_BLOCKERS = [
    "contador publico nacional", "titulo de contador", "cpa certification required",
    "certified public accountant required", "matricula habilitante",
    "titulo de abogado", "titulo habilitante de abogado", "law degree required",
    "titulo de medico", "medical degree required", "graduado en medicina",
    "titulo de ingeniero civil", "phd required", "doctorado excluyente",
    "mba required", "must hold a phd",
]

# --------------------------------------------------------------------------- #
# Skills reconocidas (para gaps y matching)
# --------------------------------------------------------------------------- #
KNOWN_SKILLS = [
    "excel", "google sheets", "sql", "python", "r", "power bi", "powerbi", "tableau",
    "looker", "google analytics", "ga4", "salesforce", "hubspot", "sap", "jira",
    "confluence", "notion", "figma", "asana", "trello", "airtable", "dbt", "bigquery",
    "snowflake", "amplitude", "mixpanel", "hotjar", "canva", "powerpoint", "word",
    "vba", "google ads", "meta ads", "seo", "sem", "crm", "erp", "scrum", "agile",
    "kanban", "data studio", "looker studio", "qlik", "spss", "stata", "matlab",
]

# Skills que, si faltan, casi nunca deberían bloquear a un perfil junior
SOFT_GAP_SKILLS = {
    "power bi", "powerbi", "tableau", "looker", "sql", "python", "r", "vba",
    "salesforce", "sap", "jira", "amplitude", "mixpanel", "dbt", "bigquery",
    "snowflake", "qlik", "spss", "stata", "looker studio",
}


def all_role_titles() -> list[tuple[str, str]]:
    """[(family_key, title), ...] para generación de queries y matching."""
    return [(fam, t) for fam, cfg in ROLE_FAMILIES.items() for t in cfg["titles"]]
