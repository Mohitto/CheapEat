"""
probe_biedronka_shop.py — jednorazowa sonda diagnostyczna.

Pytanie: czy biedronka.pl (poza gazetką, którą już mamy zreverse-
engineerowaną) publikuje GDZIEKOLWIEK regularne ceny produktów, tak jak
lidl.pl publikuje je na stronach kategorii/produktów (SSR JSON) i w
product_sitemap.xml.gz? Potrzebne, bo część promocji w gazetce Biedronki
(np. "przy zakupie 6 — supercena 53% taniej") nie podaje żadnej kwoty w
złotówkach — tylko procent od ceny regularnej, której gazetka nie zawiera.

Sprawdzamy, w kolejności, TYLKO prawdziwe, odkryte adresy (nigdy nie
zgadujemy URL-i produktowych):
1. robots.txt -> Sitemap: (standard sitemaps.org)
2. Typowe znane subdomeny/ścieżki sklepu internetowego (jeśli w ogóle
   istnieją i odpowiadają 200) — nie zgadujemy PRODUKTÓW, tylko sprawdzamy
   czy w ogóle jest jakiś publiczny katalog/sklep, z którego dałoby się
   pociągnąć realne linki tak jak zrobiliśmy dla Lidla.
3. Strona główna biedronka.pl — szukamy linków do sklepu/katalogu w HTML.
"""
import re

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

CANDIDATE_HOSTS = [
    "https://www.biedronka.pl",
    "https://www.biedronkahome.pl",
    "https://sklep.biedronka.pl",
    "https://zakupy.biedronka.pl",
]


def check_url(url: str, timeout: int = 15) -> None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        print(f"{url} -> status {resp.status_code} (finalny URL: {resp.url}), "
              f"długość: {len(resp.text)} znaków")
    except requests.RequestException as e:
        print(f"{url} -> BŁĄD: {e}")


def main():
    print("=== 1. robots.txt każdego kandydata (Sitemap:) ===")
    for host in CANDIDATE_HOSTS:
        robots_url = f"{host}/robots.txt"
        try:
            resp = requests.get(robots_url, headers=HEADERS, timeout=15)
            print(f"{robots_url} -> status {resp.status_code}")
            if resp.status_code == 200:
                sitemaps = re.findall(r'^Sitemap:\s*(\S+)', resp.text, re.IGNORECASE | re.MULTILINE)
                print(f"  Sitemap(y): {sitemaps}")
                print(f"  Pierwsze 500 znaków robots.txt: {resp.text[:500]!r}")
        except requests.RequestException as e:
            print(f"{robots_url} -> BŁĄD: {e}")

    print("\n=== 2. Czy same hosty w ogóle odpowiadają ===")
    for host in CANDIDATE_HOSTS:
        check_url(host)

    print("\n=== 3. Linki do sklepu/katalogu w HTML strony głównej biedronka.pl ===")
    try:
        resp = requests.get("https://www.biedronka.pl/", headers=HEADERS, timeout=15)
        print(f"https://www.biedronka.pl/ -> status {resp.status_code}, długość {len(resp.text)}")
        # Szukamy linków zawierających słowa sugerujące sklep/katalog/produkty.
        links = set(re.findall(r'href=["\']([^"\']+)["\']', resp.text))
        keywords = ["sklep", "produkt", "katalog", "shop", "zakup", "oferta", "asortyment"]
        matching = sorted({l for l in links if any(k in l.lower() for k in keywords)})
        print(f"Linki pasujące do słów kluczowych sklepu ({len(matching)}):")
        for l in matching[:60]:
            print(f"  {l}")
    except requests.RequestException as e:
        print(f"https://www.biedronka.pl/ -> BŁĄD: {e}")


if __name__ == "__main__":
    main()
