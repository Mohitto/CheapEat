"""
shop_scraper.py — regularne (nie-gazetkowe) ceny Biedronki z
zakupy.biedronka.pl (prawdziwy sklep internetowy, Salesforce Commerce
Cloud / Demandware, "Sites-Grocery-Biedronka-PL-Site").

Powód istnienia tego modułu (patrz scrapers/probe_biedronka_*.py): sporo
promocji w gazetce (biedronka/scraper.py) podaje TYLKO % zniżki od ceny
regularnej ("PRZY ZAKUPIE 6 — SUPERCENA 53% TANIEJ"), bez żadnej kwoty w
złotówkach — gazetka regularnej ceny bazowej po prostu nie zawiera. Dla
takich produktów (np. mleko) flyer-OCR nigdy nie wyprodukuje ceny,
niezależnie jak dobry byłby parser — potwierdzone na żywo pełnym zrzutem
OCR strony gazetki. Ten moduł uzupełnia lukę, czytając REGULARNE ceny
wprost ze sklepu internetowego.

Struktura strony (potwierdzona na żywo, patrz probe_biedronka_tile.py):
każdy kafelek produktu ma formularz "Dodaj do koszyka" z atrybutem
data-product-gtm zawierającym CZYSTY, ustrukturyzowany JSON (warstwa
danych Google Tag Manager e-commerce), np. dla PID 0000000036:
  data-product-gtm="{&quot;item_name&quot;:&quot;Mlekovita Mleko UHT 3,2 %
  tłuszczu Wypasione 1 l&quot;,&quot;item_id&quot;:&quot;0000000036&quot;,
  &quot;price&quot;:&quot;4.49&quot;,&quot;item_brand&quot;:&quot;Mlekovita&quot;,
  ...,&quot;item_category&quot;:&quot;Nabiał&quot;,&quot;item_category2&quot;:&quot;Mleko&quot;}"
Dużo prostsze niż Lidl: nie trzeba wchodzić na strony pojedynczych
produktów — strona kategorii już zawiera nazwę+cenę KAŻDEGO widocznego
produktu wprost w HTML, ustrukturyzowane, bez zgadywania i bez potrzeby
JSON-LD/OCR.

Kategorie do przeszukania to PRAWDZIWE, odkryte linki z nawigacji strony
głównej (probe_biedronka_zakupy.py), przefiltrowane do sekcji
spożywczych — nigdy nie zgadujemy URL-i.
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_or_create, get_supabase
from ingredient_catalog import (
    INGREDIENT_DEFAULTS,
    extract_unit_amount_grams,
    is_plausible,
    match_ingredient,
)

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

BASE_URL = "https://zakupy.biedronka.pl"

# Prawdziwe sekcje spożywcze odkryte na stronie głównej
# (probe_biedronka_zakupy.py) — pomijamy drogerię/dla dzieci/dla
# zwierząt/dom, bo nie mają związku ze składnikami przepisów.
GROCERY_SECTION_PREFIXES = (
    "/nabial/", "/mieso/", "/warzywa/", "/owoce/", "/piekarnia/",
    "/napoje/", "/napoje-2/", "/mrozone/", "/artykuly-spozywcze/",
    "/dania-gotowe/",
)

HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']')
# Potwierdzone na żywo na kafelku produktu (probe_biedronka_tile.py):
# JSON warstwy danych GTM osadzony jako atrybut HTML, wartości
# HTML-entity-encoded (&quot; zamiast ").
PRODUCT_GTM_PATTERN = re.compile(r'data-product-gtm="([^"]*)"')


def discover_grocery_category_urls() -> list[str]:
    """Zwraca prawdziwe linki kategorii spożywczych ze strony głównej —
    nigdy nie zgaduje URL-i."""
    resp = requests.get(BASE_URL + "/", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    links = set(HREF_PATTERN.findall(resp.text))
    matching = sorted({
        l for l in links
        if l.startswith(GROCERY_SECTION_PREFIXES) and l.endswith("/")
    })
    return [BASE_URL + l for l in matching]


def extract_products_from_category(url: str) -> list[dict]:
    """Zwraca listę {name, price, item_id} z atrybutów data-product-gtm
    osadzonych wprost w HTML strony kategorii — bez potrzeby wchodzenia
    na strony pojedynczych produktów."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"[Biedronka-sklep] {url} -> BŁĄD: {e}")
        return []
    if resp.status_code != 200:
        print(f"[Biedronka-sklep] {url} -> status {resp.status_code}, pomijam")
        return []

    products = []
    for m in PRODUCT_GTM_PATTERN.finditer(resp.text):
        raw = html.unescape(m.group(1))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        name = data.get("item_name")
        item_id = data.get("item_id")
        price_raw = data.get("price")
        if not name or not item_id or price_raw in (None, "", "0", 0):
            continue
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        products.append({"name": name, "price": price, "item_id": item_id})

    return products


class BiedronkaShopScraper:
    store_name = "Biedronka"
    store_website = "https://www.biedronka.pl"

    def __init__(self):
        self.sb = get_supabase()
        self.store_id = get_or_create(
            self.sb, "stores", {"name": self.store_name},
            {"website_url": self.store_website, "is_active": True},
        )

    def scrape(self) -> dict:
        category_urls = discover_grocery_category_urls()
        print(f"[Biedronka-sklep] Kategorii spożywczych do przeszukania: {len(category_urls)}")

        all_products: list[dict] = []
        for url in category_urls:
            products = extract_products_from_category(url)
            print(f"[Biedronka-sklep] {url} -> {len(products)} produktów")
            all_products.extend(products)

        # Porównanie "najtańszej" opcji na SUROWEJ cenie opakowania (bez
        # przeliczenia na 100g/ml) dawało błędne wyniki na żywo — np. dla
        # "mleko" wygrywał mały słoiczek mleka zsiadłego 400g za 1,99 zł
        # zamiast prawdziwego mleka 1l za 3,49 zł, mimo że to drugie jest
        # tańsze per 100ml. Trzeba znać gramaturę PRZED porównaniem, nie
        # po wybraniu "najtańszego" kandydata.
        found_per_ingredient: dict[str, dict] = {}
        for p in all_products:
            ingredient_name = match_ingredient(p["name"])
            if not ingredient_name:
                continue

            unit_amount = extract_unit_amount_grams(p["name"], ingredient_name)
            if unit_amount is None:
                # Mnóstwo produktów (zwłaszcza świeże mięso/warzywa sprzedawane
                # "za kg" bez podanej wagi opakowania w nazwie) nie da się
                # bezpiecznie przeliczyć — zbyt liczne, by logować każdy bez DEBUG.
                if DEBUG:
                    print(f"[Biedronka-sklep] Pomijam '{p['name']}' — brak gramatury/ilości w nazwie")
                continue

            price_per_100 = round(p["price"] / (unit_amount / 100.0), 4)
            if DEBUG:
                print(f"[Biedronka-sklep] Dopasowano '{p['name']}' -> {ingredient_name} "
                      f"({p['price']} zł, {price_per_100} zł/100)")

            candidate = {**p, "unit_amount": unit_amount, "price_per_100": price_per_100}
            if ingredient_name not in found_per_ingredient or price_per_100 < found_per_ingredient[ingredient_name]["price_per_100"]:
                found_per_ingredient[ingredient_name] = candidate

        saved = self._save(found_per_ingredient)
        return {
            "categories_scanned": len(category_urls),
            "products_seen": len(all_products),
            "ingredients_found": len(found_per_ingredient),
            "saved": saved,
        }

    def _save(self, found_per_ingredient: dict[str, dict]) -> int:
        if not found_per_ingredient:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        # Ceny regularne zmieniają się rzadziej niż promocje z gazetki
        # (3-4 dni) — okno ważności dłuższe, ale wciąż odświeżane
        # codziennie przez ten sam harmonogram co pozostałe scrapery.
        valid_to = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        saved = 0

        for ingredient_name, p in found_per_ingredient.items():
            unit_amount = p["unit_amount"]
            price_per_100 = p["price_per_100"]
            if not is_plausible(ingredient_name, price_per_100):
                print(f"[Biedronka-sklep] Odrzucam nieprawdopodobną cenę: {ingredient_name} -> "
                      f"{price_per_100} zł/100 (z '{p['name']}', {p['price']} zł za {unit_amount:g}g)")
                continue

            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = f"{p['name']} (Biedronka, cena regularna)"
            store_product_id = get_or_create(
                self.sb, "store_products",
                {"store_id": self.store_id, "name": product_name},
                {"unit": "g", "unit_amount": unit_amount},
            )

            self.sb.table("prices").insert({
                "store_product_id": store_product_id,
                "gross_price": p["price"],
                "source": "shop-regular",
                "valid_from": today,
                "valid_to": valid_to,
            }).execute()

            existing_mapping = self.sb.table("ingredient_mappings").select("id") \
                .eq("ingredient_id", ingredient_id) \
                .eq("store_product_id", store_product_id).limit(1).execute()
            if not existing_mapping.data:
                self.sb.table("ingredient_mappings").insert({
                    "ingredient_id": ingredient_id,
                    "store_product_id": store_product_id,
                    "conversion_factor": round(unit_amount / 100, 4),
                    "priority": 15,
                }).execute()

            saved += 1

        return saved


if __name__ == "__main__":
    result = BiedronkaShopScraper().scrape()
    print(f"\n[Biedronka-sklep] Podsumowanie: {result}")
