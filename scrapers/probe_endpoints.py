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

GENERIC_PAGES = [
    ("Biedronka home.biedronka.pl/promocje", "https://home.biedronka.pl/promocje/"),
]

LIDL_PROMO_URL = "https://www.lidl.pl/c/promocje/s10076831"
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


def probe_lidl_deep(url: str) -> None:
    print(f"\n{'='*70}")
    print(f"Lidl DEEP EXTRACT -> {url}")
    print("=" * 70)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    page_html = resp.text
    unescaped = html_module.unescape(page_html)

    # Znajdź custom elementy przenoszące stan (Web Components z SSR hydration)
    tags_found = set()
    for tag, attr in STATE_ATTR_PATTERN.findall(page_html):
        tags_found.add((tag.lower(), attr.lower()))
    print(f"\n-- Custom elementy ze stanem (tag, atrybut): {sorted(tags_found)[:20]} --")

    # Znajdź wszystkie wystąpienia klucza "price" poprzedzonego "currencyCode"
    # w ODESCAPOWANYM tekście i wyciągnij zbalansowany obiekt JSON zawierający je,
    # cofając się do najbliższego '{' przed dopasowaniem.
    needle = '"currencyCode":"PLN"'
    count = unescaped.count(needle)
    print(f"\n-- Wystąpień {needle!r} po html.unescape: {count} --")

    shown = 0
    pos = 0
    while shown < 3:
        idx = unescaped.find(needle, pos)
        if idx == -1:
            break

        # Zawsze pokaż surowy kontekst — niezawodne, niezależnie od tego czy
        # bracket-matching poniżej trafi we właściwy obiekt.
        ctx_start = max(0, idx - 1500)
        print(f"\n-- Surowy kontekst wokół wystąpienia #{shown+1} (offset {idx}): --")
        print(unescaped[ctx_start:idx + 300])

        # Znajdź NAJMNIEJSZY obiekt {...} który faktycznie OBEJMUJE idx —
        # idąc wstecz po kolejnych '{' i sprawdzając, czy jego zbalansowany
        # zasięg sięga za idx (poprzednia wersja tego po prostu zgadywała
        # drugi rfind, co czasem łapało zupełnie inny, sąsiedni obiekt).
        search_pos = idx
        blob = None
        for _ in range(20):
            brace_idx = unescaped.rfind('{', 0, search_pos)
            if brace_idx == -1:
                break
            end = _extract_balanced_json(unescaped, brace_idx)
            if end is not None and brace_idx + len(end) > idx:
                blob = end
                break
            search_pos = brace_idx

        print(f"-- Kandydat #{shown+1} zbalansowany obiekt, długość={len(blob) if blob else 0} --")
        if blob:
            print(blob[:3000])
            try:
                parsed = json.loads(blob)
                print(f"  [JSON OK] klucze top-level: {list(parsed.keys())[:30]}")
            except Exception as e:
                print(f"  [JSON PARSE FAIL] {e}")
        shown += 1
        pos = idx + len(needle)


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


def main():
    for name, url in GENERIC_PAGES:
        probe(name, url)

    probe_lidl_deep(LIDL_PROMO_URL)

    for api_url in LIDL_API_CANDIDATES:
        probe_bare_api(api_url)


if __name__ == "__main__":
    main()
