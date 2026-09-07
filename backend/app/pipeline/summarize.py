"""Resumen del aviso, extraído del propio texto.

NO genera texto nuevo: segmenta la descripción por sus encabezados y devuelve
las frases que ya están escritas. Es una decisión deliberada — el sistema no
puede inventar requisitos ni tareas (§53 del brief), y sin LLM no hay forma
honesta de redactar un resumen propio.

Lo que sí hace es sacar el relleno: la mitad de un aviso corporativo es
"somos líderes en...", y eso no aporta nada para decidir si aplicar.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.pipeline.text import clean_text

# --------------------------------------------------------------------------- #
# Encabezados de sección, en los tres idiomas que aparecen en la práctica
# --------------------------------------------------------------------------- #
SECCIONES: list[tuple[str, re.Pattern]] = [
    ("responsabilidades", re.compile(
        r"^(principales\s+desaf[ií]os|desaf[ií]os|responsabilidades|tus\s+(tareas|responsabilidades)|"
        r"funciones|misi[oó]n|qu[eé]\s+har[aá]s|tu\s+d[ií]a\s+a\s+d[ií]a|el\s+rol|sobre\s+el\s+(rol|puesto)|"
        r"what\s+you.?ll\s+do|responsibilities|key\s+responsibilities|the\s+role|your\s+impact|"
        r"your\s+role|about\s+the\s+role|in\s+this\s+role|day\s+to\s+day|"
        r"deine\s+aufgaben|aufgaben|ihre\s+aufgaben)\b[:\s]*$", re.I)),
    ("requisitos", re.compile(
        r"^(requisitos?|requerimientos|qu[eé]\s+(buscamos|necesitamos)|lo\s+que\s+buscamos|"
        r"tu\s+perfil|perfil|perfil\s+buscado|conocimientos\s+requeridos|"
        r"requirements?|qualifications|minimum\s+qualifications|basic\s+qualifications|"
        r"what\s+you.?ll\s+bring|what\s+we.?re\s+looking\s+for|who\s+you\s+are|"
        r"skills\s+and\s+experience|dein\s+profil|anforderungen|"
        r"what\s+we\s+need\s+from\s+you)\b[:\s]*$", re.I)),
    ("deseables", re.compile(
        r"^(deseables?|se\s+valorar[aá]|valoramos|diferenciales?|opcional|"
        r"preferred\s+qualifications|nice\s+to\s+have|bonus\s+points|"
        r"preferred|a\s+plus|plus|wünschenswert|von\s+vorteil)\b[:\s]*$", re.I)),
    ("beneficios", re.compile(
        r"^(beneficios?|qu[eé]\s+ofrecemos|ofrecemos|te\s+ofrecemos|nuestros\s+beneficios|"
        r"benefits?|what\s+we\s+offer|perks|compensation\s+and\s+benefits|"
        r"wir\s+bieten|unsere\s+benefits)\b[:\s]*$", re.I)),
]

# Bloques que son puro relleno corporativo o metadatos del ATS
RUIDO = re.compile(
    r"^(about\s+(us|the\s+company|our)|sobre\s+(nosotros|la\s+empresa)|qui[eé]nes\s+somos|"
    r"our\s+(company|culture|values|mission|commitment)|nuestra\s+(cultura|misi[oó]n)|"
    r"equal\s+opportunit|igualdad\s+de\s+oportunidades|diversity|diversidad\s+e\s+inclusi|"
    r"job\s+(category|details|description\s*&?\s*summary|type|id|requisition)|"
    r"line\s+of\s+service|industry/?sector|specialism|management\s+level|"
    r"travel\s+requirements|government\s+clearance|posting\s+date|"
    r"accommodation|privacy|cookie|terms\s+of|aviso\s+legal)\b", re.I)

RUIDO_FRASE = re.compile(
    r"(somos\s+(l[ií]der|la\s+empresa\s+l[ií]der)|l[ií]der(es)?\s+en\s+el\s+mercado|"
    r"we\s+are\s+(the|a)\s+(#?1|leading|global\s+leader)|"
    r"equal\s+opportunity\s+employer|empleador\s+que\s+ofrece\s+igualdad|"
    r"consider(ing)?\s+applying\s+for\s+a\s+maximum|"
    r"all\s+qualified\s+applicants|sin\s+distinci[oó]n\s+de)", re.I)

VINETA = re.compile(r"^\s*(?:[-•·*–—▪●○]|\d{1,2}[.)])\s+")
ENCABEZADO_GENERICO = re.compile(r"^[A-ZÁÉÍÓÚÑ][^.!?]{2,60}:?$")

MAX_ITEMS = 6
MAX_LARGO = 240

# Para elegir el overview: preferimos la frase que habla del PUESTO, no la que
# habla de la empresa. "Somos líderes en..." no ayuda a decidir si aplicar.
SENIAL_PUESTO = re.compile(
    r"(sumate\s+como|buscamos\s+(un|una|a)|nos\s+encontramos\s+buscando|"
    r"como\s+\w+[,\s]+(vas\s+a|ser[aá]s|tendr[aá]s)|en\s+este\s+rol|"
    r"as\s+(a|an|our)\s+[\w\s/&-]{3,40}[,\s]+you|you\s+will\s+(be|join|work|own|help)|"
    r"in\s+this\s+role|this\s+role|the\s+opportunity|we\s+are\s+looking\s+for|"
    r"join\s+(our|us)\s+as|you.?ll\s+(be|join|work|own))", re.I)

SENIAL_EMPRESA = re.compile(
    r"^(somos|we\s+are|our\s+(company|team|mission)|nuestra\s+(empresa|comunidad|misi[oó]n)|"
    r"contamos\s+con|fundad[ao]|founded|back\s+in\s+\d{4}|"
    r"con\s+m[aá]s\s+de\s+\d+\s+a[ñn]os|te\s+invitamos\s+a\s+sumarte)", re.I)


@dataclass
class DescriptionDigest:
    """Lo que el aviso dice, sin el relleno."""

    overview: str = ""
    responsabilidades: list[str] = field(default_factory=list)
    requisitos: list[str] = field(default_factory=list)
    deseables: list[str] = field(default_factory=list)
    beneficios: list[str] = field(default_factory=list)
    palabras: int = 0
    lectura_min: int = 0
    cobertura: str = "sin_descripcion"   # completo | parcial | sin_descripcion

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def tiene_contenido(self) -> bool:
        return bool(self.overview or self.responsabilidades or self.requisitos)


def _limpiar_item(linea: str) -> str:
    texto = clean_text(VINETA.sub("", linea))
    texto = re.sub(r"\s*[:;]\s*$", "", texto)
    if len(texto) > MAX_LARGO:
        corte = texto[:MAX_LARGO].rsplit(" ", 1)[0]
        texto = corte + "…"
    return texto


def _es_util(texto: str, dentro_de_seccion: bool = False) -> bool:
    if len(texto) < 6 or len(texto) > 400:
        return False
    if RUIDO.match(texto) or RUIDO_FRASE.search(texto):
        return False
    # Fuera de una sección, dos palabras suelen ser un rótulo del ATS ("Sales",
    # "Not Applicable"). Dentro, son requisitos legítimos: "Inglés avanzado",
    # "Excel avanzado", "Alemán C1".
    if not dentro_de_seccion and len(texto.split()) <= 3:
        return False
    return True


def _detectar_seccion(linea: str) -> str | None:
    plano = clean_text(linea).rstrip(":").strip()
    if len(plano) > 70:
        return None
    for nombre, patron in SECCIONES:
        if patron.match(plano):
            return nombre
    return None


def summarize_description(descripcion: str | None) -> DescriptionDigest:
    """Segmenta el aviso y devuelve sus partes útiles, tal como están escritas."""
    digest = DescriptionDigest()
    if not descripcion or len(descripcion.strip()) < 40:
        return digest

    palabras = len(descripcion.split())
    digest.palabras = palabras
    digest.lectura_min = max(1, round(palabras / 220))

    # Los párrafos vienen cortados en varias líneas: se reunen antes de analizar,
    # si no el overview queda partido a la mitad.
    lineas: list[str] = []
    buffer: list[str] = []

    def _volcar() -> None:
        if buffer:
            lineas.append(" ".join(buffer))
            buffer.clear()

    for cruda in descripcion.splitlines():
        texto = clean_text(cruda)
        if not texto:
            _volcar()
            continue
        if VINETA.match(cruda) or _detectar_seccion(texto):
            _volcar()
            lineas.append(cruda)
            continue
        # Una línea continúa a la anterior si aquella no cerró la oración y ésta
        # arranca en minúscula. Es la señal de un párrafo cortado por el ancho.
        continua = (
            buffer
            and not buffer[-1].rstrip().endswith((".", "!", "?", ":", ";"))
            and texto[:1].islower()
        )
        if continua:
            buffer.append(texto)
        else:
            _volcar()
            buffer.append(texto)
    _volcar()

    seccion: str | None = None
    buckets: dict[str, list[str]] = {
        "responsabilidades": [], "requisitos": [], "deseables": [], "beneficios": [],
    }
    libres: list[str] = []

    for linea in lineas:
        crudo = clean_text(linea)
        if not crudo:
            continue

        nueva = _detectar_seccion(crudo)
        if nueva:
            seccion = nueva
            continue
        # Un encabezado que no reconocemos igual corta la sección anterior
        if ENCABEZADO_GENERICO.match(crudo) and len(crudo.split()) <= 6:
            if RUIDO.match(crudo):
                seccion = None
            continue

        item = _limpiar_item(crudo)
        if not _es_util(item, dentro_de_seccion=bool(seccion)):
            continue

        if seccion:
            if len(buckets[seccion]) < MAX_ITEMS:
                buckets[seccion].append(item)
        elif VINETA.match(linea):
            # Viñeta suelta antes de cualquier encabezado: suele ser una tarea
            if len(buckets["responsabilidades"]) < MAX_ITEMS:
                buckets["responsabilidades"].append(item)
        else:
            libres.append(item)

    digest.responsabilidades = buckets["responsabilidades"]
    digest.requisitos = buckets["requisitos"]
    digest.deseables = buckets["deseables"]
    digest.beneficios = buckets["beneficios"]

    # El overview: se prefiere la frase que describe el puesto sobre la que
    # describe la empresa.
    def _puntaje(parrafo: str) -> float:
        puntos = 0.0
        if SENIAL_PUESTO.search(parrafo):
            puntos += 10.0
        if SENIAL_EMPRESA.match(parrafo):
            puntos -= 6.0
        palabras = len(parrafo.split())
        if 14 <= palabras <= 60:
            puntos += 2.0
        elif palabras < 12:
            puntos -= 3.0
        return puntos

    candidatos = [p for p in libres if len(p.split()) >= 8]
    if candidatos:
        mejor = max(candidatos, key=_puntaje)
        # Si ninguno habla del puesto, el primero sirve igual como contexto
        digest.overview = mejor if _puntaje(mejor) > 0 else candidatos[0]

    encontradas = sum(1 for v in buckets.values() if v)
    if encontradas >= 2 and digest.overview:
        digest.cobertura = "completo"
    elif encontradas or digest.overview:
        digest.cobertura = "parcial"
    return digest
