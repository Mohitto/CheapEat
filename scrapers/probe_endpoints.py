"""
probe_endpoints.py — jednorazowy skrypt diagnostyczny (NIE część produkcyjnego
pipeline'u scraperów). Cel: znaleźć prawdziwe adresy API/gazetek Biedronki
i Lidla, żeby dało się naprawić biedronka/scraper.py i lidl/scraper.py.

Poprzednie próby (BIEDRONKA_API = ".../offers-api", LIDL_API = ".../api/offers")
były zgadywanką napisaną bez dostępu do internetu — obie zwróciły 404/HTML
zamiast JSON (patrz debug_*_error_body.txt z uruchomienia scrape-flyers.yml).

Ten skrypt NIE zgaduje kolejnych URLi na oślep — zamiast tego pobiera strony,
które WIEMY że są dostępne (200 OK), i szuka w ich treści:
  1. linków <a href> zawierających słowa kluczowe (gazetka/promocje/oferty/leaflet)
  2. osadzonego JSON-a (Next.js __NEXT_DATA__, window.__INITIAL_STATE__ itp.)
  3. dowolnych stringów wyglądających jak endpoint API (/api/, /graphql, .json)

Output idzie na stdout (nie do plików), żeby dało się go odczytać bezpośrednio
z logów GitHub Actions bez pobierania artefaktu (blob storage jest poza
allowlistą sieciową środowiska deweloperskiego).
"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

PAGES = [
    # Runda 1 (poprzednie odpalenie) namierzyła te dwie strony jako
    # najbardziej obiecujące realne źródła cen/gazetek:
    ("Lidl promocje (kategoria)", "https://www.lidl.pl/c/promocje/s10076831"),
    ("Biedronka gazetka (press viewer)",
     "https://www.biedronka.pl/pl/press,id,j0pu3be7s,title,codziennie-niskie-ceny-p-oferta-od-03-09"),
]

KEYWORDS = ["gazet", "promo", "ofert", "leaflet", "flyer", "katalog"]
API_PATTERN = re.compile(r"[\"']([^\"'\s]{0,200}(?:/api/|/graphql|\.json)[^\"'\s]{0,100})[\"']", re.IGNORECASE)
LINK_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
SCRIPT_ID_PATTERN = re.compile(r'<script[^>]*id=["\'](__NEXT_DATA__|__INITIAL_STATE__|__NUXT__)["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
INLINE_ASSIGN_PATTERN = re.compile(r'window\.(__\w+__|\w*[Ss]tate\w*|\w*[Dd]ata\w*|dataLayer)\s*=\s*(\[?\{.{0,300})', re.DOTALL)
JSONLD_PATTERN = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
FRAMEWORK_MARKERS = ["data-reactroot", "ng-version", "__NUXT__", "id=\"__next\"", "data-vue", "webpack"]


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

    html = resp.text

    print(f"\n-- Pierwsze 2000 znaków surowego HTML: --")
    print(html[:2000])

    print(f"\n-- Wystąpienia 'zł' w HTML: {html.count('zł')} --")

    found_markers = [m for m in FRAMEWORK_MARKERS if m in html]
    print(f"\n-- Markery frameworka JS znalezione: {found_markers} --")

    # 1. Linki z gazetkowymi słowami kluczowymi
    links = set(LINK_PATTERN.findall(html))
    matching_links = sorted({l for l in links if any(k in l.lower() for k in KEYWORDS)})
    print(f"\n-- Linki zawierające {KEYWORDS}: {len(matching_links)} --")
    for l in matching_links[:30]:
        print(f"  {l}")

    # 2. JSON-LD (schema.org) — czasem zawiera Product/Offer z ceną
    jsonld_blobs = JSONLD_PATTERN.findall(html)
    print(f"\n-- Bloków JSON-LD: {len(jsonld_blobs)} --")
    for blob in jsonld_blobs[:5]:
        print(blob[:800])
        print("  ...")

    # 3. Next.js / initial-state JSON
    for match_id, blob in SCRIPT_ID_PATTERN.findall(html):
        print(f"\n-- Znaleziono <script id=\"{match_id}\"> ({len(blob)} znaków), pierwsze 2000: --")
        print(blob[:2000])

    for var_name, blob in INLINE_ASSIGN_PATTERN.findall(html):
        print(f"\n-- Znaleziono window.{var_name} = ... , pierwsze 500 znaków: --")
        print(blob[:500])

    # 4. Stringi wyglądające jak endpointy API
    api_hits = sorted(set(API_PATTERN.findall(html)))
    print(f"\n-- Stringi wyglądające jak API endpoint: {len(api_hits)} --")
    for hit in api_hits[:40]:
        print(f"  {hit}")

    # 5. Fragment wokół pierwszego wystąpienia 'zł' — realny przykład ceny w HTML
    idx = html.find('zł')
    if idx != -1:
        start = max(0, idx - 300)
        print(f"\n-- Kontekst wokół pierwszego 'zł' (offset {idx}): --")
        print(html[start:idx + 100])


def main():
    for name, url in PAGES:
        probe(name, url)


if __name__ == "__main__":
    main()
