"""
probe_biedronka_zakupy.py — druga runda sondy.

probe_biedronka_shop.py ustalił, że zakupy.biedronka.pl realnie
odpowiada (200, ~320 KB HTML) i jego robots.txt ma wzorce typowe dla
Salesforce Commerce Cloud/Demandware (dwvar, Product-Variation,
variantID, pid=) — czyli to prawdopodobnie prawdziwy sklep internetowy
z realnymi cenami. Ta sonda szuka PRAWDZIWYCH linków kategorii/produktów
w HTML strony głównej (nigdy nie zgaduje URL-i) i sprawdza, czy strony
produktowe ujawniają cenę (JSON-LD schema.org, albo cokolwiek innego
strukturalnego, jak przy Lidlu).
"""
import re

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

BASE = "https://zakupy.biedronka.pl"


def main():
    resp = requests.get(BASE + "/", headers=HEADERS, timeout=20)
    print(f"{BASE}/ -> status {resp.status_code}, długość {len(resp.text)}")
    html = resp.text

    # Wszystkie linki href, żeby zobaczyć realną strukturę URL-i tego sklepu.
    links = sorted(set(re.findall(r'href=["\']([^"\']+)["\']', html)))
    print(f"\n=== Wszystkie unikalne linki href na stronie głównej ({len(links)}) ===")
    for l in links[:150]:
        print(f"  {l}")

    # Czy jest JSON-LD na stronie głównej (czasem jest Organization/WebSite,
    # ale sprawdźmy czy w ogóle mechanizm jest używany na tej platformie).
    jsonld_count = len(re.findall(r'application/ld\+json', html, re.IGNORECASE))
    print(f"\n=== application/ld+json na stronie głównej: {jsonld_count} wystąpień ===")

    # Szukamy w HTML jakichkolwiek cen w formacie X,XX zł (żeby sprawdzić,
    # czy strona główna w ogóle pokazuje ceny).
    prices = re.findall(r'\d{1,3},\d{2}\s*zł', html)
    print(f"\n=== Ceny 'X,XX zł' znalezione bezpośrednio w HTML strony głównej: {len(prices)} ===")
    print(prices[:20])

    # Typowe dla Demandware/SFCC: szukaj śladów danych produktowych w
    # inline <script> (często jest to dataLayer / analytics z cenami).
    datalayer_hits = re.findall(r'(?:price|Price)["\':]\s*["\']?(\d+(?:[.,]\d+)?)', html)
    print(f"\n=== Wzorzec '\"price\": liczba' w HTML/JS strony głównej: {len(datalayer_hits)} ===")
    print(datalayer_hits[:20])


if __name__ == "__main__":
    main()
