"""
probe_endpoints.py — jednorazowy skrypt diagnostyczny (NIE część produkcyjnego
pipeline'u scraperów). Cel: znaleźć prawdziwe adresy API/gazetek Biedronki
i Lidla, żeby dało się naprawić biedronka/scraper.py i lidl/scraper.py.

Historia (patrz poprzednie uruchomienia w Actions -> Probe Store Endpoints):
- Runda 1: BIEDRONKA_API/LIDL_API zgadywane bez internetu -> 404 / HTML.
  Znaleziono za to realne strony: Lidl `/c/promocje/s10076831`,
  Biedronka `press,id,...` (viewer gazetki).
- Runda 2: Lidl `/c/promocje/...` to SSR-owana strona Nuxt —
  `window.__NUXT__.config` zawiera `searchPath: /q/api/search` i
  `gridboxesPath: /q/api/gridboxes`, a w treści strony jest prawdziwy JSON
  produktów z cenami PLN (potwierdzone przez `"currencyCode":"PLN"`,
  `"currencySymbol":"zł"`). Biedronka `press,id,...` to czysty flipbook
  viewer (0 wystąpień "zł", brak frameworka JS) — prawdopodobnie
  obrazki/PDF, nie tekst.
- Runda 3 (ten plik): głębsza ekstrakcja JSON-a produktów z Lidla (pełny
  obiekt, nie tylko fragment) + próba bezpośredniego strzału w
  /q/api/gridboxes i /q/api/search + sprawdzenie home.biedronka.pl/promocje
  jako alternatywnego, może tekstowego źródła ofert Biedronki.

Output idzie na stdout (nie do plików), żeby dało się go odczytać bezpośrednio
z logów GitHub Actions bez pobierania artefaktu (blob storage jest poza
allowlistą sieciową środowiska deweloperskiego).
"""
import html as html_module
import json
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

GENERIC_PAGES = []

# Runda 4 potwierdziła: pełny obiekt produktu w SSR HTML Lidla ma schemat
# {..., "keyfacts": {"title", "fullTitle", ...}, "price": {"currencyCode",
# "price", "oldPrice", "discount", ...}, "image", "ians", ...}. Ale
# /c/promocje/s10076831 to WYŁĄCZNIE nie-spożywcze produkty tygodnia
# (rolety, koszule, kurtki) — typowe dla dyskontów "oferty tygodnia" osobno
# od zwykłych spożywczych. Do przepisów potrzebujemy działu spożywczego,
# więc ta runda szuka linku do takiej kategorii w nawigacji i sprawdza, czy
# ten sam schemat (i pole gramatury/jednostki, którego jeszcze nie widzieliśmy)
# występuje tam.
LIDL_PROMO_URL = "https://www.lidl.pl/c/promocje/s10076831"
LIDL_NAV_SOURCE_URL = "https://www.lidl.pl/"
GROCERY_KEYWORDS = ["spozywcze", "nabial", "pieczywo", "mieso", "wedlin", "napoje",
                     "swiez", "owoce", "warzywa", "mrozon", "produkty-spozywcze"]
LIDL_API_CANDIDATES = [
    "https://www.lidl.pl/q/api/gridboxes",
    "https://www.lidl.pl/q/api/search",
]

KEYWORDS = ["gazet", "promo", "ofert", "leaflet", "flyer", "katalog"]
API_PATTERN = re.compile(r"[\"']([^\"'\s]{0,200}(?:/api/|/graphql|\.json)[^\"'\s]{0,100})[\"']", re.IGNORECASE)
LINK_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
SCRIPT_ID_PATTERN = re.compile(r'<script[^>]*id=["\'](__NEXT_DATA__|__INITIAL_STATE__|__NUXT__)["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
INLINE_ASSIGN_PATTERN = re.compile(r'window\.(__\w+__|\w*[Ss]tate\w*|\w*[Dd]ata\w*|dataLayer)\s*=\s*(\[?\{.{0,300})', re.DOTALL)
JSONLD_PATTERN = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
FRAMEWORK_MARKERS = ["data-reactroot", "ng-version", "__NUXT__", "id=\"__next\"", "data-vue", "webpack"]
STATE_ATTR_PATTERN = re.compile(r'<([a-z][a-z0-9-]*)\s[^>]*?\b(data-state|data-props|state|props)=["\']', re.IGNORECASE)


def probe(name: str, url: str) -> None:
    print(f"\n{'='*70}")
    print(f"{name} -> {url}")
    print("=" * 70)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} content-type={resp.headers.get('content-type')} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    page_html = resp.text

    print(f"\n-- Pierwsze 2000 znaków surowego HTML: --")
    print(page_html[:2000])

    print(f"\n-- Wystąpienia 'zł' w HTML: {page_html.count('zł')} --")

    found_markers = [m for m in FRAMEWORK_MARKERS if m in page_html]
    print(f"\n-- Markery frameworka JS znalezione: {found_markers} --")

    links = set(LINK_PATTERN.findall(page_html))
    matching_links = sorted({l for l in links if any(k in l.lower() for k in KEYWORDS)})
    print(f"\n-- Linki zawierające {KEYWORDS}: {len(matching_links)} --")
    for l in matching_links[:30]:
        print(f"  {l}")

    jsonld_blobs = JSONLD_PATTERN.findall(page_html)
    print(f"\n-- Bloków JSON-LD: {len(jsonld_blobs)} --")
    for blob in jsonld_blobs[:5]:
        print(blob[:800])
        print("  ...")

    for match_id, blob in SCRIPT_ID_PATTERN.findall(page_html):
        print(f"\n-- Znaleziono <script id=\"{match_id}\"> ({len(blob)} znaków), pierwsze 2000: --")
        print(blob[:2000])

    for var_name, blob in INLINE_ASSIGN_PATTERN.findall(page_html):
        print(f"\n-- Znaleziono window.{var_name} = ... , pierwsze 500 znaków: --")
        print(blob[:500])

    api_hits = sorted(set(API_PATTERN.findall(page_html)))
    print(f"\n-- Stringi wyglądające jak API endpoint: {len(api_hits)} --")
    for hit in api_hits[:40]:
        print(f"  {hit}")

    idx = page_html.find('zł')
    if idx != -1:
        start = max(0, idx - 300)
        print(f"\n-- Kontekst wokół pierwszego 'zł' (offset {idx}): --")
        print(page_html[start:idx + 100])


def _extract_balanced_json(text: str, start_brace_idx: int) -> str | None:
    """Zwraca podciąg text[start_brace_idx:...] będący jednym zbalansowanym {...}."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start_brace_idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_brace_idx:i + 1]
    return None


def probe_lidl_deep(name: str, url: str, max_shown: int = 3) -> None:
    print(f"\n{'='*70}")
    print(f"Lidl DEEP EXTRACT [{name}] -> {url}")
    print("=" * 70)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    page_html = resp.text
    unescaped = html_module.unescape(page_html)

    needle = '"currencyCode":"PLN"'
    count = unescaped.count(needle)
    print(f"\n-- Wystąpień {needle!r} po html.unescape: {count} --")

    shown = 0
    pos = 0
    while shown < max_shown:
        idx = unescaped.find(needle, pos)
        if idx == -1:
            break

        # Znajdź obiekt PRODUKTU (zawiera i "keyfacts" i "price":{...}), nie
        # tylko najmniejszy obiekt obejmujący idx (to byłby sam "price").
        # Idziemy wstecz po kolejnych '{', licząc zbalansowany zasięg każdego,
        # aż trafimy na taki, który sięga za idx ORAZ zawiera "keyfacts".
        search_pos = idx
        blob = None
        for _ in range(40):
            brace_idx = unescaped.rfind('{', 0, search_pos)
            if brace_idx == -1:
                break
            end = _extract_balanced_json(unescaped, brace_idx)
            if end is not None and brace_idx + len(end) > idx and '"keyfacts"' in end:
                blob = end
                break
            search_pos = brace_idx

        print(f"\n-- Produkt #{shown+1}, długość obiektu={len(blob) if blob else 0} --")
        if blob:
            try:
                parsed = json.loads(blob)
                keyfacts = parsed.get("keyfacts", {})
                price = parsed.get("price", {})
                print(f"  nazwa: {keyfacts.get('fullTitle') or keyfacts.get('title')}")
                print(f"  cena: {price.get('price')} {price.get('currencySymbol')} (było: {price.get('oldPrice')})")
                other_keys = [k for k in parsed.keys()
                              if k not in ("keyfacts", "price", "image", "image_V1", "imageList",
                                           "imageList_V1", "gs1Attributes", "guaranteeLabels", "ians")]
                print(f"  pozostałe klucze top-level: {other_keys}")
                # Pola, które mogłyby nieść gramaturę/jednostkę
                for k in other_keys:
                    v = parsed[k]
                    if isinstance(v, (str, int, float, bool)) and any(
                        hint in k.lower() for hint in ("unit", "gram", "quant", "pack", "measur", "weight", "volum")
                    ):
                        print(f"    kandydat na gramaturę/jednostkę: {k}={v!r}")
            except Exception as e:
                print(f"  [JSON PARSE FAIL] {e}")
                print(f"  surowy fragment: {blob[:1000]}")
        else:
            ctx_start = max(0, idx - 500)
            print(f"  Nie znaleziono obiektu produktu — surowy kontekst:")
            print(unescaped[ctx_start:idx + 200])
        shown += 1
        pos = idx + len(needle)


def find_grocery_link(nav_url: str) -> str | None:
    print(f"\n{'='*70}")
    print(f"Szukam linku do kategorii spożywczej w nawigacji -> {nav_url}")
    print("=" * 70)
    try:
        resp = requests.get(nav_url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return None

    links = set(LINK_PATTERN.findall(resp.text))
    hits = sorted({l for l in links if any(k in l.lower() for k in GROCERY_KEYWORDS)})
    print(f"-- Linki spożywcze znalezione: {len(hits)} --")
    for l in hits[:30]:
        print(f"  {l}")

    if not hits:
        return None
    chosen = hits[0]
    if chosen.startswith("/"):
        chosen = "https://www.lidl.pl" + chosen
    return chosen


IMAGE_PATTERN = re.compile(r'["\']([^"\']+\.(?:jpe?g|png|webp|gif))(?:[?"\']|$)', re.IGNORECASE)
PDF_PATTERN = re.compile(r'["\']([^"\']+\.pdf)(?:[?"\']|$)', re.IGNORECASE)
INLINE_SCRIPT_PATTERN = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)


def probe_biedronka_flipbook(url: str) -> None:
    """Biedronka press,id,... to viewer oparty o createjs (canvas). Cel: czy
    strony gazetki to osadzone obrazki/PDF z realnym tekstem, czy czysto
    zeskanowane bitmapy bez warstwy tekstowej. Jeśli znajdziemy PDF z
    warstwą tekstową, to najprostsza droga do prawdziwych cen Biedronki —
    bez OCR. Jeśli tylko obrazki, OCR (pytesseract) to następny krok."""
    print(f"\n{'='*70}")
    print(f"Biedronka FLIPBOOK PROBE -> {url}")
    print("=" * 70)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    page_html = resp.text

    pdf_hits = sorted(set(PDF_PATTERN.findall(page_html)))
    print(f"\n-- Linki .pdf: {len(pdf_hits)} --")
    for l in pdf_hits[:20]:
        print(f"  {l}")

    image_hits = sorted(set(IMAGE_PATTERN.findall(page_html)))
    print(f"\n-- Linki do obrazków (jpg/png/webp/gif): {len(image_hits)} --")
    for l in image_hits[:40]:
        print(f"  {l}")

    # Inline <script> (bez src) — tu prawdopodobnie config flipbooka
    # (lista stron, bazowy URL obrazków, itp.)
    inline_scripts = INLINE_SCRIPT_PATTERN.findall(page_html)
    print(f"\n-- Inline <script> bloków: {len(inline_scripts)} --")
    for i, blob in enumerate(inline_scripts):
        stripped = blob.strip()
        if not stripped:
            continue
        keywords = ["page", "gazet", "press", "config", "issuu", "flipbook", "cdn", ".jpg", ".png"]
        if any(k in stripped.lower() for k in keywords):
            print(f"\n  -- Script #{i} ({len(stripped)} znaków), zawiera słowo kluczowe --")
            print(f"  {stripped[:1500]}")

            # Dla dużych bloków (prawdopodobnie pełna struktura flipbooka)
            # szukamy dowodów na hotspoty produktowe (cena/nazwa osadzone
            # jako dane obok współrzędnych, mimo że strona to bitmapa).
            if len(stripped) > 5000:
                hotspot_keywords = ["hotspot", "cena", "price", "produkt", "sku", "zł", "PLN", "title"]
                found = {k: stripped.lower().count(k.lower()) for k in hotspot_keywords}
                print(f"    Wystąpienia słów kluczowych w tym bloku: {found}")
                for kw in hotspot_keywords:
                    kidx = stripped.lower().find(kw.lower())
                    if kidx != -1:
                        ctx_s = max(0, kidx - 200)
                        print(f"    -- kontekst wokół '{kw}' (offset {kidx}) --")
                        print(f"    {stripped[ctx_s:kidx + 300]}")
                # Też: struktura "pages" — pokaż fragment po słowie 'pages'
                pidx = stripped.find("pages")
                if pidx != -1:
                    print(f"    -- kontekst wokół 'pages' (offset {pidx}) --")
                    print(f"    {stripped[pidx:pidx + 1500]}")


def probe_bare_api(url: str) -> None:
    print(f"\n{'='*70}")
    print(f"BARE API PROBE -> {url}")
    print("=" * 70)
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=20)
        print(f"status={resp.status_code} content-type={resp.headers.get('content-type')} bytes={len(resp.content)}")
        print(resp.text[:1500])
    except Exception as e:
        print(f"[FETCH ERROR] {e}")


BIEDRONKA_PRESS_URLS = [
    "https://www.biedronka.pl/pl/press,id,j0pu3be7s,title,codziennie-niskie-ceny-p-oferta-od-03-09",
]


def main():
    # Runda 7: Biedronka jest priorytetem dla użytkownika (bliżej, częściej
    # testowana) mimo że Lidl już działa. Sprawdzamy czy flipbook viewer
    # (createjs-based) ładuje strony jako PDF z warstwą tekstową (najlepszy
    # przypadek — parsowalne bez OCR) czy jako czyste obrazki (wymaga OCR).
    for url in BIEDRONKA_PRESS_URLS:
        probe_biedronka_flipbook(url)


if __name__ == "__main__":
    main()
