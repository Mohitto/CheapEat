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
from base_scraper import get_or_create, get_supabase, replace_price
from ingredient_catalog import (
    INGREDIENT_DEFAULTS,
    is_plausible,
    match_ingredient,
    parse_package_spec,
    unit_for,
    unit_price_of,
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

# Sklep podaje wielkość opakowania WPROST, własnym polem (potwierdzone na
# żywo, probe_biedronka_promo.py):
#   <div class="packaging-details">10szt.<span> - 1,40 zł / szt</span></div>
#   <div class="packaging-details">0.2kg<span> - 29,95 zł / kg</span></div>
# To źródło jest lepsze niż zgadywanie gramatury regexem z nazwy produktu:
# jest deklarowane przez sam sklep i od razu mówi, czy produkt sprzedaje
# się na sztuki czy na wagę.
PACKAGING_DETAILS_PATTERN = re.compile(
    r'class="packaging-details"[^>]*>\s*([\d.,]+)\s*(szt\.?|kg|g|l|ml)\b',
    re.IGNORECASE,
)
TILE_SPLIT_PATTERN = re.compile(r'<div class="product-tile\b')


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


def parse_packaging_details(tile_html: str) -> tuple[str, float] | None:
    """Wielkość opakowania z pola `packaging-details` danego kafelka,
    znormalizowana do ("szt"|"g"|"ml", ilość). Zwraca None, gdy kafelek
    tego pola nie ma (np. produkty na wagę sprzedawane "za kg")."""
    m = PACKAGING_DETAILS_PATTERN.search(tile_html)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower().rstrip(".")
    if unit == "szt":
        return ("szt", amount)
    if unit == "kg":
        return ("g", amount * 1000)
    if unit == "l":
        return ("ml", amount * 1000)
    return (unit, amount)


def extract_products_from_category(url: str) -> list[dict]:
    """Zwraca listę {name, price, item_id, unit, unit_amount} — po jednym
    wpisie na kafelek produktu. Nazwa i cena pochodzą z data-product-gtm,
    a wielkość opakowania z pola packaging-details TEGO SAMEGO kafelka
    (dlatego tniemy HTML na kafelki zamiast szukać obu wzorców globalnie —
    inaczej gramatura jednego produktu trafiłaby do ceny innego)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"[Biedronka-sklep] {url} -> BŁĄD: {e}")
        return []
    if resp.status_code != 200:
        print(f"[Biedronka-sklep] {url} -> status {resp.status_code}, pomijam")
        return []

    products = []
    for tile in TILE_SPLIT_PATTERN.split(resp.text)[1:]:
        m = PRODUCT_GTM_PATTERN.search(tile)
        if not m:
            continue
        try:
            data = json.loads(html.unescape(m.group(1)))
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

        spec = parse_packaging_details(tile)
        products.append({
            "name": name,
            "price": price,
            "item_id": item_id,
            "unit": spec[0] if spec else None,
            "unit_amount": spec[1] if spec else None,
        })

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

        # Porównanie "najtańszej" opcji musi iść po cenie JEDNOSTKOWEJ
        # (zł/100g, zł/100ml albo zł/szt), nie po surowej cenie opakowania —
        # inaczej mały słoiczek za 1,99 zł wygrywa z litrem mleka za 3,49 zł,
        # mimo że jest droższy w przeliczeniu.
        found_per_ingredient: dict[str, dict] = {}
        for p in all_products:
            ingredient_name = match_ingredient(p["name"])
            if not ingredient_name:
                continue

            # Najpierw to, co sklep deklaruje wprost (packaging-details);
            # dopiero gdy kafelek tego nie ma — próba wyczytania z nazwy.
            unit, unit_amount = p["unit"], p["unit_amount"]
            if unit is None:
                spec = parse_package_spec(p["name"], ingredient_name)
                if spec is None:
                    # Świeże mięso/warzywa "za kg" nie mają stałego opakowania —
                    # zbyt liczne, żeby logować każde bez DEBUG.
                    if DEBUG:
                        print(f"[Biedronka-sklep] Pomijam '{p['name']}' — brak wielkości opakowania")
                    continue
                unit, unit_amount = spec

            unit_price = unit_price_of(ingredient_name, p["price"], unit, unit_amount)
            if unit_price is None:
                if DEBUG:
                    print(f"[Biedronka-sklep] Pomijam '{p['name']}' — opakowanie w '{unit}', "
                          f"a {ingredient_name} liczymy w '{unit_for(ingredient_name)}'")
                continue

            if DEBUG:
                print(f"[Biedronka-sklep] Dopasowano '{p['name']}' -> {ingredient_name} "
                      f"({p['price']} zł za {unit_amount:g}{unit}, {round(unit_price, 4)} zł/j.)")

            candidate = {**p, "unit": unit, "unit_amount": unit_amount, "unit_price": unit_price}
            if ingredient_name not in found_per_ingredient or unit_price < found_per_ingredient[ingredient_name]["unit_price"]:
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
            unit, unit_amount, unit_price = p["unit"], p["unit_amount"], p["unit_price"]
            if not is_plausible(ingredient_name, unit_price):
                print(f"[Biedronka-sklep] Odrzucam nieprawdopodobną cenę: {ingredient_name} -> "
                      f"{round(unit_price, 4)} zł/j. (z '{p['name']}', {p['price']} zł "
                      f"za {unit_amount:g}{unit})")
                continue

            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = f"{p['name']} (Biedronka, cena regularna)"
            store_product_id = get_or_create(
                self.sb, "store_products",
                {"store_id": self.store_id, "name": product_name},
                {"unit": unit, "unit_amount": unit_amount},
            )
            # Wielkość opakowania mogła się zmienić od poprzedniego przebiegu
            # (albo pochodzić ze starej, gorszej heurystyki) — wyrównaj.
            self.sb.table("store_products").update(
                {"unit": unit, "unit_amount": unit_amount}
            ).eq("id", store_product_id).execute()

            replace_price(self.sb, store_product_id, "shop-regular",
                          p["price"], today, valid_to)

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
