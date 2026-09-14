"""
probe_biedronka_promo.py — czy sklep online Biedronki ujawnia ceny PROMOCYJNE?

Kontekst: użytkownik zgłosił, że apka pokazuje masło 5,99 zł, podczas gdy
w Biedronce jest teraz promocja ~2,50 zł. Nasz shop_scraper.py bierze pole
"price" z data-product-gtm — trzeba sprawdzić, czy to cena regularna czy
już promocyjna, i czy obok jest cena przekreślona / cena omnibus / znacznik
promocji, którego nie czytamy.

Ta sonda wycina JEDEN pełny kafelek produktu (od <div class="product-tile
do znacznika końca) i szuka w HTML kategorii typowych markerów promocji.
"""
import re

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

BASE = "https://zakupy.biedronka.pl"
# /promocje i /polecane/promocje/ to prawdziwe linki z nawigacji strony
# głównej (probe_biedronka_zakupy.py) — jeśli sklep online w ogóle
# publikuje ceny promocyjne w sposób strukturalny, to właśnie tam.
CATEGORIES = ["/promocje", "/polecane/promocje/", "/nabial/maslo/"]

PROMO_MARKERS = [
    "promocj", "omnibus", "regularna", "najniższa", "przekreśl",
    "strike", "was-price", "old-price", "price--old", "discount",
    "rabat", "taniej", "oszczędz", "sale",
]


def probe(path: str) -> None:
    url = BASE + path
    resp = requests.get(url, headers=HEADERS, timeout=30)
    html = resp.text
    print(f"\n{'='*70}\n{url} -> status {resp.status_code}, długość {len(html)}\n{'='*70}")

    # 0. Jakie warianty "opakowania ceny" występują — price--default to
    # cena regularna; jakikolwiek inny wariant oznaczałby promocję.
    wrappers = re.findall(r'price-tile__wrapper\s+([a-z0-9_-]+)', html, re.IGNORECASE)
    counts: dict[str, int] = {}
    for w in wrappers:
        counts[w] = counts.get(w, 0) + 1
    print(f"warianty price-tile__wrapper: {counts}")

    strikethrough = re.findall(r'class="[^"]*price[^"]*(?:strike|old|was|regular|previous)[^"]*"', html, re.IGNORECASE)
    print(f"klasy sugerujące cenę przekreśloną/regularną: {sorted(set(strikethrough))[:10]}")

    # 1. Markery promocji w całym HTML kategorii
    low = html.lower()
    for marker in PROMO_MARKERS:
        count = low.count(marker)
        if count:
            idx = low.find(marker)
            snippet = html[max(0, idx - 120):idx + 160].replace("\n", " ")
            print(f"[marker '{marker}'] wystąpień: {count} -> ...{snippet}...")

    # 2. Wszystkie bloki data-product-gtm (co dokładnie mamy w JSON-ie)
    gtm = re.findall(r'data-product-gtm="([^"]*)"', html)
    print(f"\ndata-product-gtm bloków: {len(gtm)}")
    for g in gtm[:3]:
        print(f"  {g[:400]}")

    # 3. Jeden PEŁNY kafelek produktu — żeby zobaczyć wszystkie ceny w środku
    start = html.find('<div class="product-tile')
    if start != -1:
        end = html.find('END: .product-tile', start)
        tile = html[start:end + 40] if end != -1 else html[start:start + 6000]
        # Zredukuj puste linie, żeby log był czytelny
        tile = re.sub(r'\n\s*\n+', '\n', tile)
        print(f"\n--- PEŁNY KAFELEK ({len(tile)} znaków) ---")
        print(tile[:6000])
        print("--- koniec kafelka ---")

    # 4. Wszystkie kwoty "X,XX zł" wraz z 60 znakami kontekstu przed nimi
    print("\n--- kwoty z kontekstem ---")
    for m in list(re.finditer(r'\d{1,3},\d{2}\s*zł', html))[:20]:
        ctx = html[max(0, m.start() - 90):m.end() + 20].replace("\n", " ")
        ctx = re.sub(r'\s+', ' ', ctx)
        print(f"  {m.group(0):12s} <- ...{ctx}...")


if __name__ == "__main__":
    for c in CATEGORIES:
        try:
            probe(c)
        except requests.RequestException as e:
            print(f"{BASE}{c} -> BŁĄD: {e}")
