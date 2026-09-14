"""
probe_biedronka_category.py — trzecia runda sondy.

zakupy.biedronka.pl to prawdziwy sklep internetowy Biedronki (Salesforce
Commerce Cloud, "Sites-Grocery-Biedronka-PL-Site") z realną nawigacją
kategorii dokładnie pokrywającą się z naszymi składnikami: /nabial/mleko/,
/nabial/jaja/, /nabial/maslo/, /mieso/drob/, itd. — prawdziwe, odkryte
linki z rundy 2, nie zgadywane.

Ta sonda wchodzi na kilka z tych kategorii i sprawdza:
1. Czy strona kategorii pokazuje realne ceny produktów wprost w HTML.
2. Czy jest JSON-LD (schema.org Product/Offer) na stronie kategorii.
3. Jakie linki do POJEDYNCZYCH produktów są na niej (żeby wiedzieć, czy
   trzeba wejść głębiej, jak przy Lidlu).
"""
import re

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

BASE = "https://zakupy.biedronka.pl"
CATEGORIES = ["/nabial/mleko/", "/nabial/jaja/", "/nabial/maslo/"]


def probe_category(path: str) -> None:
    url = BASE + path
    resp = requests.get(url, headers=HEADERS, timeout=20)
    html = resp.text
    print(f"\n{'='*70}\n{url} -> status {resp.status_code}, długość {len(html)}\n{'='*70}")

    jsonld_count = len(re.findall(r'application/ld\+json', html, re.IGNORECASE))
    print(f"application/ld+json wystąpień: {jsonld_count}")
    if jsonld_count:
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.IGNORECASE | re.DOTALL,
        )
        for b in blocks[:3]:
            print(f"--- JSON-LD blok (pierwsze 800 znaków) ---\n{b[:800]}")

    prices = re.findall(r'\d{1,3}[,.]\d{2}\s*zł', html)
    print(f"Ceny 'X,XX zł' w HTML: {len(prices)} -> {prices[:15]}")

    # Linki do pojedynczych stron produktowych SFCC zwykle mają wzorzec
    # /nazwa-produktu/kod.html lub podobny .html z myślnikami.
    product_links = sorted(set(re.findall(r'href=["\']([^"\']+\.html)["\']', html)))
    non_blog = [l for l in product_links if "/blog/" not in l and "regulamin" not in l]
    print(f"Linki .html (nie blog/regulamin): {len(non_blog)}")
    for l in non_blog[:20]:
        print(f"  {l}")

    # Szukaj typowych dla SFCC atrybutów danych produktowych w HTML (np.
    # data-pid, itemprop="price", pricing).
    data_pids = re.findall(r'data-pid=["\']([^"\']+)["\']', html)
    print(f"data-pid znalezione: {len(set(data_pids))} -> przykłady: {sorted(set(data_pids))[:10]}")

    itemprop_price = re.findall(r'itemprop=["\']price["\'][^>]*content=["\']([^"\']+)["\']', html)
    print(f"itemprop=price: {itemprop_price[:10]}")


if __name__ == "__main__":
    for cat in CATEGORIES:
        try:
            probe_category(cat)
        except requests.RequestException as e:
            print(f"{BASE}{cat} -> BŁĄD: {e}")
