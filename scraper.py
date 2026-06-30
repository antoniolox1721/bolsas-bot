"""
Scraper for IST scholarship recruitment editais.

Fetches the listing table at
https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/, downloads each edital
PDF, extracts its text and matches it against a set of keywords for the
Electrical Engineering area (Engenharia Eletrotecnica e de Computadores / DEEC).

Designed to run standalone (``python scraper.py``) or be imported by the bot.
"""

from __future__ import annotations

import concurrent.futures
import re
import time
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

import requests
from bs4 import BeautifulSoup

# pypdf is the maintained package; PyPDF2 is the legacy fallback.
try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader


LISTING_URL = "https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/"
USER_AGENT = "Mozilla/5.0 (compatible; BolsasBot/1.0; +scholarship-watcher)"
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------
# All keywords are matched against text that has been lower-cased and had its
# accents stripped, so write them here WITHOUT accents and in lower case.
#
# CORE      -> high precision, almost certainly Electrical Engineering (DEEC).
# RELATED   -> sub-areas of DEEC; broader, may occasionally over-match.
# Tune these freely; the bot reports which keyword matched so you can calibrate.
CORE_KEYWORDS = [
    "engenharia eletrotecnica",
    "engenharia electrotecnica",
    "eletrotecnica",
    "electrotecnica",
    "meec",          # Mestrado em Eng. Eletrotecnica e de Computadores
    "leec",          # Licenciatura "
    "deec",          # Departamento "
]

RELATED_KEYWORDS = [
    "eletronica",
    "electronica",
    "microeletronica",
    "telecomunicacoes",
    "sistemas de energia",
    "energia eletrica",
    "redes de energia",
    "maquinas eletricas",
    "acionamentos",
    "eletronica de potencia",
    "processamento de sinal",
    "sistemas de decisao e controlo",
    "instrumentacao",
    "fotonica",
]

DEFAULT_KEYWORDS = CORE_KEYWORDS + RELATED_KEYWORDS


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Lower-case, strip accents and collapse whitespace for robust matching."""
    return re.sub(r"\s+", " ", strip_accents(text).lower())


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Bolsa:
    vagas: str = ""
    tipo: str = ""
    responsavel: str = ""
    area_projeto: str = ""        # "Area / Projeto" column = the scholarship topic
    edital_code: str = ""         # e.g. "IST 2026 BL127"
    data_abertura: str = ""
    prazo: str = ""
    pdf_url: str = ""
    # filled in after the PDF is parsed:
    area_cientifica: str = ""     # the official "area cientifica" of the edital
    nivel: str = ""               # target degree level (Licenciatura/Mestrado/...)
    matched: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.area_projeto or self.edital_code or self.pdf_url


# ---------------------------------------------------------------------------
# Listing page
# ---------------------------------------------------------------------------
def fetch_listings(session: requests.Session | None = None) -> list[Bolsa]:
    """Parse the recruitment table into Bolsa objects (no PDF download yet)."""
    sess = session or requests.Session()
    resp = sess.get(LISTING_URL, headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    bolsas: list[Bolsa] = []
    for row in soup.select("table tr"):
        link = row.find("a", href=re.compile(r"\.pdf", re.I))
        if not link:
            continue  # header / language-toggle / non-data rows
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        # Data rows look like:
        # [vagas, tipo, responsavel, area/projeto, (empty), edital, abertura, prazo]
        def cell(i: int) -> str:
            return cells[i] if i < len(cells) else ""

        edital = cell(5) or cell(4)
        bolsas.append(Bolsa(
            vagas=cell(0),
            tipo=cell(1),
            responsavel=cell(2),
            area_projeto=cell(3),
            edital_code=edital,
            data_abertura=cell(6),
            prazo=cell(7),
            pdf_url=requests.compat.urljoin(LISTING_URL, link["href"]),
        ))
    return bolsas


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------
_AREA_RE = re.compile(r"area cientifica de\s+(.+)", re.I)


def extract_pdf_text(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(url, headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    reader = PdfReader(BytesIO(resp.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def find_area_cientifica(raw_text: str) -> str:
    """Return the 'area cientifica de ...' phrase as it appears in the edital.

    The PDFs use the 'fi' ligature (U+FB01), so 'cientifica' is stored as
    'cientiﬁca'. NFKC normalization fixes the ligature while keeping accents,
    so the result is still nicely readable (e.g. 'Engenharia eletrotecnica').
    """
    text = unicodedata.normalize("NFKC", raw_text)
    m = re.search(
        r"[aá]rea cient[ií]fica de\s+(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def match_keywords(raw_text: str, keywords: list[str]) -> list[str]:
    norm = normalize(raw_text)
    return [kw for kw in keywords if kw in norm]


def classify_level(tipo: str, raw_text: str) -> str:
    """Determine the target degree level (público-alvo) of a scholarship.

    Combines three signals, most authoritative first:
      1. The 'tipo de bolsa' column (e.g. 'Estudante de Doutoramento', 'Pós-Doutoral').
      2. The PDF header line 'para alunos matriculados em curso de <X>'.
      3. The admission section, for 'Iniciação à Investigação' bolsas that target
         students by study cycle ('1.º ou 2.º ciclo') or degree name.

    Returns a friendly label such as 'Doutoramento', 'Mestrado', 'Licenciatura',
    'Licenciatura / Mestrado', 'Curso não conferente a grau' or 'Pós-Doutoramento'.
    """
    tipo_n = normalize(tipo)
    text_n = normalize(raw_text)

    # 1. Post-doc and non-degree are unambiguous from the tipo column.
    if "pos-doutoral" in tipo_n or "pos-doutoramento" in tipo_n:
        return "Pós-Doutoramento"
    if "nao conferente" in tipo_n:
        return "Curso não conferente a grau"

    # 2. 'Estudante de <level>' (tipo) or the 'matriculados em curso de <level>'
    #    header line (PDF) — authoritative for these bolsas.
    word_label = {"doutoramento": "Doutoramento",
                  "mestrado": "Mestrado",
                  "licenciatura": "Licenciatura"}
    m = re.search(r"matriculad[oa]s? em curso (?:de )?(doutoramento|mestrado|licenciatura)",
                  text_n)
    if m:
        return word_label[m.group(1)]
    if re.search(r"matriculad[oa]s? em curso nao conferente", text_n):
        return "Curso não conferente a grau"
    for word, label in word_label.items():
        if f"estudante de {word}" in tipo_n:
            return label

    # 3. Iniciação à Investigação (and similar): inspect the admission section.
    idx = text_n.find("requisitos")
    section = text_n[idx:idx + 700] if idx != -1 else text_n[:700]

    levels: list[str] = []
    # Study cycles, possibly listed together: "1.º ou 2.º ciclo".
    cyc = re.search(r"((?:[123]\.?\s*o\s*(?:ou|e|a|/|,)?\s*)+)ciclo", section)
    if cyc:
        cycle_label = {"1": "Licenciatura", "2": "Mestrado", "3": "Doutoramento"}
        for n in re.findall(r"[123]", cyc.group(1)):
            if cycle_label[n] not in levels:
                levels.append(cycle_label[n])
    # Explicit degree names.
    for word, label in word_label.items():
        if word in section and label not in levels:
            levels.append(label)

    order = ["Licenciatura", "Mestrado", "Doutoramento"]
    levels.sort(key=lambda x: order.index(x) if x in order else 99)
    return " / ".join(levels)


# ---------------------------------------------------------------------------
# High-level search
# ---------------------------------------------------------------------------
def _enrich(bolsa: Bolsa, keywords: list[str],
            session: requests.Session) -> Bolsa:
    try:
        text = extract_pdf_text(bolsa.pdf_url, session)
    except Exception:
        # If a PDF fails, fall back to matching the listing-row text only.
        text = " ".join([bolsa.area_projeto, bolsa.tipo])
    bolsa.area_cientifica = find_area_cientifica(text)
    bolsa.nivel = classify_level(bolsa.tipo, text)
    bolsa.matched = match_keywords(text, keywords)
    return bolsa


def search_bolsas(keywords: list[str] | None = None,
                  max_workers: int = 8) -> list[Bolsa]:
    """Return the bolsas whose edital matches any of the keywords."""
    keywords = keywords or DEFAULT_KEYWORDS
    session = requests.Session()
    listings = fetch_listings(session)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        enriched = list(ex.map(lambda b: _enrich(b, keywords, session), listings))

    return [b for b in enriched if b.matched]


# ---------------------------------------------------------------------------
# Tiny TTL cache (so repeated bot commands don't re-scrape every time)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, list[Bolsa]]] = {}
CACHE_TTL = 300  # seconds


def search_bolsas_cached(keywords: list[str] | None = None) -> list[Bolsa]:
    key = ",".join(keywords or DEFAULT_KEYWORDS)
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL:
        return _cache[key][1]
    result = search_bolsas(keywords)
    _cache[key] = (now, result)
    return result


if __name__ == "__main__":
    import sys
    extra = sys.argv[1:]
    kws = DEFAULT_KEYWORDS + [normalize(k) for k in extra]
    print(f"Scraping {LISTING_URL} ...")
    hits = search_bolsas(kws)
    print(f"\n{len(hits)} matching bolsa(s) for Electrical Engineering:\n")
    for b in hits:
        print(f"• {b.name}")
        print(f"    tipo: {b.tipo or 'n/a'}")
        print(f"    nivel: {b.nivel or 'n/a'}")
        if b.area_cientifica:
            print(f"    area cientifica: {b.area_cientifica}")
        print(f"    matched: {', '.join(b.matched)}")
        print(f"    prazo: {b.prazo or 'n/a'}")
        print(f"    {b.pdf_url}\n")
