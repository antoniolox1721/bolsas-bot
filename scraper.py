import concurrent.futures as cf, re, time, unicodedata
from dataclasses import dataclass, field
from io import BytesIO
import requests
from bs4 import BeautifulSoup
try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

URL = "https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/"
LISTING_URL = URL
UA = "Mozilla/5.0 (compatible; BolsasBot/1.0)"

# area -> (label, keywords)  -- keywords lower-case, no accents
AREAS = {
    "eletrotecnica": ("Engenharia Eletrotécnica", [
        "engenharia eletrotecnica", "engenharia electrotecnica", "eletrotecnica",
        "electrotecnica", "meec", "leec", "deec", "eletronica", "electronica",
        "microeletronica", "telecomunicacoes", "sistemas de energia",
        "energia eletrica", "redes de energia", "maquinas eletricas",
        "acionamentos", "eletronica de potencia", "processamento de sinal",
        "sistemas de decisao e controlo", "instrumentacao", "fotonica"]),
    "informatica": ("Engenharia Informática e de Computadores", [
        "engenharia informatica", "informatica", "leic", "meic",
        "ciencia de computadores", "ciencias da computacao", "machine learning",
        "aprendizagem automatica", "inteligencia artificial",
        "redes de computadores", "base de dados", "bases de dados",
        "seguranca informatica", "algoritmos", "sistemas distribuidos",
        "engenharia de computadores"]),
    "mecanica": ("Engenharia Mecânica", [
        "engenharia mecanica", "mecanica", "memec", "termodinamica",
        "mecanica dos fluidos", "transferencia de calor", "mecanica estrutural",
        "elementos finitos", "vibracoes", "automovel", "manufatura", "fabrico",
        "projeto mecanico", "sistemas mecanicos"]),
    "aeroespacial": ("Engenharia Aeroespacial", [
        "engenharia aeroespacial", "aeroespacial", "aeronautica", "aerodinamica",
        "avionica", "uav", "satelite", "espaco", "propulsao", "voo", "drone"]),
    "civil": ("Engenharia Civil", [
        "engenharia civil", "civil", "estruturas", "geotecnia", "hidraulica",
        "construcao", "betao", "urbanismo", "transportes", "vias",
        "ambiente construido"]),
    "materiais": ("Engenharia de Materiais", [
        "engenharia de materiais", "engenharia dos materiais", "materiais",
        "ciencia dos materiais", "metalurgia", "polimeros", "ceramicos",
        "compositos", "nanomateriais", "corrosao"]),
    "fisica": ("Engenharia Física Tecnológica", [
        "engenharia fisica", "engenharia fisica tecnologica", "fisica",
        "fisica tecnologica", "optica", "laser", "plasma", "nuclear", "fotonica",
        "quantica", "particulas"]),
    "quimica": ("Engenharia Química", [
        "engenharia quimica", "quimica", "engenharia biologica",
        "processos quimicos", "catalise", "reatores", "termoquimica",
        "biotecnologia"]),
    "biomedica": ("Engenharia Biomédica", [
        "engenharia biomedica", "biomedica", "biomedicina", "imagem medica",
        "sinais biomedicos", "biomateriais", "instrumentacao biomedica"]),
    "ambiente": ("Engenharia do Ambiente", [
        "engenharia do ambiente", "ambiental", "tratamento de agua", "residuos",
        "energia renovavel", "sustentabilidade", "poluicao", "ecologia"]),
    "naval": ("Engenharia e Arquitetura Naval", [
        "engenharia naval", "arquitetura naval", "naval", "oceanica",
        "hidrodinamica", "navios", "offshore", "submarino", "oleoduto",
        "estruturas maritimas"]),
    "gestao": ("Engenharia e Gestão Industrial", [
        "engenharia e gestao industrial", "gestao industrial", "logistica",
        "investigacao operacional", "cadeia de abastecimento",
        "gestao de operacoes"]),
}
DEFAULT_AREA = "eletrotecnica"
AREA_PROFILES = AREAS  # back-compat alias

list_areas = lambda: list(AREAS)
area_label = lambda a: AREAS.get(a, (a,))[0]
get_keywords = lambda a: AREAS.get(a, AREAS[DEFAULT_AREA])[1]


def _n(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower())


@dataclass
class Bolsa:
    vagas: str = ""
    tipo: str = ""
    responsavel: str = ""
    area_projeto: str = ""
    edital_code: str = ""
    data_abertura: str = ""
    prazo: str = ""
    pdf_url: str = ""
    area_cientifica: str = ""
    nivel: str = ""
    matched: list = field(default_factory=list)

    @property
    def name(self):
        return self.area_projeto or self.edital_code or self.pdf_url


def fetch_listings(s):
    r = s.get(URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    out = []
    for row in BeautifulSoup(r.text, "html.parser").select("table tr"):
        a = row.find("a", href=re.compile(r"\.pdf", re.I))
        if not a:
            continue
        c = [x.get_text(" ", strip=True) for x in row.find_all(["td", "th"])]
        g = lambda i: c[i] if i < len(c) else ""
        out.append(Bolsa(g(0), g(1), g(2), g(3), g(5) or g(4), g(6), g(7),
                         requests.compat.urljoin(URL, a["href"])))
    return out


def pdf_text(url, s):
    r = s.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(r.content)).pages)


def area_cientifica(text):
    m = re.search(r"[aá]rea cient[ií]fica de\s+(.+?)(?:\n|$)",
                  unicodedata.normalize("NFKC", text), re.I)
    return m.group(1).strip() if m else ""


def _region(text):
    n = _n(text)
    i = n.find("requisitos")
    return n.split("objetivos", 1)[0][:600] + " " + (n[i:i + 900] if i != -1 else "")


def matched(text, kws):
    r = _region(text)
    return [k for k in kws if k in r]


def level(tipo, text):
    t, n = _n(tipo), _n(text)
    if "pos-doutoral" in t or "pos-doutoramento" in t:
        return "Pós-Doutoramento"
    if "nao conferente" in t:
        return "Curso não conferente a grau"
    w = {"doutoramento": "Doutoramento", "mestrado": "Mestrado", "licenciatura": "Licenciatura"}
    m = re.search(r"matriculad[oa]s? em curso (?:de )?(doutoramento|mestrado|licenciatura)", n)
    if m:
        return w[m.group(1)]
    if re.search(r"matriculad[oa]s? em curso nao conferente", n):
        return "Curso não conferente a grau"
    for k, v in w.items():
        if f"estudante de {k}" in t:
            return v
    i = n.find("requisitos")
    sec = n[i:i + 700] if i != -1 else n[:700]
    found = []
    cyc = re.search(r"((?:[123]\.?\s*o\s*(?:ou|e|a|/|,)?\s*)+)ciclo", sec)
    if cyc:
        cl = {"1": "Licenciatura", "2": "Mestrado", "3": "Doutoramento"}
        found = [cl[d] for d in re.findall(r"[123]", cyc.group(1)) if cl[d] not in found]
    for k, v in w.items():
        if k in sec and v not in found:
            found.append(v)
    found.sort(key=lambda x: ["Licenciatura", "Mestrado", "Doutoramento"].index(x))
    return " / ".join(found)


def _enrich(b, kws, s):
    try:
        t = pdf_text(b.pdf_url, s)
    except Exception:
        t = b.area_projeto + " " + b.tipo
    b.area_cientifica, b.nivel, b.matched = area_cientifica(t), level(b.tipo, t), matched(t, kws)
    return b


def search_bolsas(area=DEFAULT_AREA):
    kws, s = get_keywords(area), requests.Session()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        return [b for b in ex.map(lambda b: _enrich(b, kws, s), fetch_listings(s)) if b.matched]


_cache = {}


def search_bolsas_cached(area=DEFAULT_AREA):
    now = time.time()
    if area in _cache and now - _cache[area][0] < 300:
        return _cache[area][1]
    _cache[area] = (now, search_bolsas(area))
    return _cache[area][1]


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AREA
    if a not in AREAS:
        sys.exit(f"areas: {', '.join(list_areas())}")
    hits = search_bolsas(a)
    print(f"{len(hits)} bolsa(s) for {area_label(a)}:\n")
    for b in hits:
        print(f"• {b.name}\n  {b.tipo} · {b.nivel} · {b.area_cientifica}\n  {b.prazo} · {b.pdf_url}\n")
