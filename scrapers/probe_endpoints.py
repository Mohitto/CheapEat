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
    ("Biedronka gazetki", "https://www.biedronka.pl/pl/gazetki"),
    ("Biedronka homepage", "https://www.biedronka.pl/"),
    ("Lidl homepage", "https://www.lidl.pl/"),
]

KEYWORDS = ["gazet", "promo", "ofert", "leaflet", "flyer", "katalog"]
API_PATTERN = re.compile(r"[\"']([^\"'\s]{0,200}(?:/api/|/graphql|\.json)[^\"'\s]{0,100})[\"']", re.IGNORECASE)
LINK_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
SCRIPT_ID_PATTERN = re.compile(r'<script[^>]*id=["\'](__NEXT_DATA__|__INITIAL_STATE__)["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
INLINE_ASSIGN_PATTERN = re.compile(r'window\.(__\w+__|\w*[Ss]tate\w*|\w*[Dd]ata\w*)\s*=\s*(\{.{0,300})', re.DOTALL)


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

    # 1. Linki z gazetkowymi słowami kluczowymi
    links = set(LINK_PATTERN.findall(html))
    matching_links = sorted({l for l in links if any(k in l.lower() for k in KEYWORDS)})
    print(f"\n-- Linki zawierające {KEYWORDS}: {len(matching_links)} --")
    for l in matching_links[:30]:
        print(f"  {l}")

    # 2. Next.js / initial-state JSON
    for match_id, blob in SCRIPT_ID_PATTERN.findall(html):
        print(f"\n-- Znaleziono <script id=\"{match_id}\"> ({len(blob)} znaków), pierwsze 1500: --")
        print(blob[:1500])

    for var_name, blob in INLINE_ASSIGN_PATTERN.findall(html):
        print(f"\n-- Znaleziono window.{var_name} = ... , pierwsze 500 znaków: --")
        print(blob[:500])

    # 3. Stringi wyglądające jak endpointy API
    api_hits = sorted(set(API_PATTERN.findall(html)))
    print(f"\n-- Stringi wyglądające jak API endpoint: {len(api_hits)} --")
    for hit in api_hits[:40]:
        print(f"  {hit}")


def main():
    for name, url in PAGES:
        probe(name, url)


if __name__ == "__main__":
    main()
