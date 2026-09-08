"""
Scraper gazetki/cen Lidl — realny pipeline oparty na SSR-embedded JSON.

Ustalone przez scrapers/probe_endpoints.py (rundy 2-6): strony kategorii
lidl.pl (Nuxt, SSR) osadzają w statycznym HTML pełne obiekty produktowe
jako HTML-entity-encoded JSON, np.:
  {"...", "keyfacts": {"fullTitle": "..."}, "price": {"currencyCode":"PLN",
   "price": 12.99, "oldPrice": 13.99, ...}, ...}
Potwierdzone na żywo: kategoria /c/zywnosc-i-napoje/s10068374 zwróciła
prawdziwy produkt spożywczy ("Barszcz ukraiński", 12.99 zł).

Prawdziwe wewnętrzne API (/q/api/search, /q/api/gridboxes) istnieje, ale
zwraca 406/404 na proste zapytania — wymaga dalszej reverse-engineeringu
dokładnego kształtu żądania (prawdopodobnie POST z konkretnym body).
V1 tego scrapera celowo NIE zgaduje tego kształtu — zamiast tego parsuje
to, co faktycznie jest w statycznym HTML (SSR), co daje mniej pozycji na
przebieg, ale są to zawsze prawdziwe dane, nigdy zmyślone.

Jedna kategoria SSR ujawnia tylko garstkę produktów (te które akurat są
wyróżnione na stronie), więc żeby zwiększyć szansę trafienia w nasze
kategorie, DOODKRYWAMY podkategorie spożywcze z nawigacji strony głównej
kategorii (linki /c/.../s\\d+ zawierające słowa kluczowe typu "nabial",
"jaja", "pieczywo", "mieso") i skanujemy też je — zamiast zgadywać ich
URL-e na oślep.
"""
import html as html_module
import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_supabase
from ingredient_catalog import AVERAGE_UNIT_WEIGHT_G, INGREDIENT_DEFAULTS, is_plausible, match_ingredient

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

# Punkt startowy, zweryfikowany na żywo (patrz docstring). Stąd
# doodkrywamy podkategorie zamiast zgadywać ich URL-e.
ROOT_GROCERY_URL = "https://www.lidl.pl/c/zywnosc-i-napoje/s10068374"

SUBCATEGORY_LINK_PATTERN = re.compile(r'href=["\'](/c/[a-z0-9-]+/s\d+)["\']', re.IGNORECASE)
SUBCATEGORY_KEYWORDS = [
    "nabial", "jaj", "pieczywo", "mieso", "wedlin", "ryb", "mrozon",
    "swiez", "napoj", "przetwor", "slodycz", "owoc", "warzyw", "nabiał",
]
MAX_SUBCATEGORIES = 15


def get_or_create(sb, table: str, match: dict, defaults: dict | None = None) -> str:
    query = sb.table(table).select("id")
    for key, value in match.items():
        query = query.eq(key, value)
    res = query.limit(1).execute()
    if res.data:
        return res.data[0]["id"]
    ins = sb.table(table).insert({**match, **(defaults or {})}).execute()
    return ins.data[0]["id"]


def _extract_balanced_json(text: str, start_brace_idx: int) -> str | None:
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


def discover_grocery_subcategories(html: str) -> list[str]:
    """Wyciąga linki do podkategorii spożywczych z nawigacji strony
    kategorii — zamiast zgadywać URL-e, znajdujemy prawdziwe."""
    links = set(SUBCATEGORY_LINK_PATTERN.findall(html))
    root_path = ROOT_GROCERY_URL.replace("https://www.lidl.pl", "")
    if DEBUG:
        print(f"[Lidl] Znaleziono {len(links)} linków /c/.../sNNN łącznie na stronie startowej")
        for l in sorted(links)[:40]:
            print(f"[Lidl]   kandydat: {l}")

    matching = sorted({l for l in links if l != root_path and any(k in l.lower() for k in SUBCATEGORY_KEYWORDS)})
    return ["https://www.lidl.pl" + l for l in matching[:MAX_SUBCATEGORIES]]


def extract_products_from_category(url: str) -> tuple[list[dict], str]:
    """Zwraca (lista {title, price, old_price} osadzonych w SSR, surowy HTML)
    — surowy HTML jest potrzebny tylko dla strony startowej, żeby
    doodkryć podkategorie."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[Lidl] {url} -> status {resp.status_code}, pomijam")
        return [], ""

    unescaped = html_module.unescape(resp.text)
    needle = '"currencyCode":"PLN"'
    products = []
    pos = 0

    while True:
        idx = unescaped.find(needle, pos)
        if idx == -1:
            break

        search_pos = idx
        blob = None
        for _ in range(40):
            brace_idx = unescaped.rfind('{', 0, search_pos)
            if brace_idx == -1:
                break
            end = _extract_balanced_json(unescaped, brace_idx)
            if end is not None and brace_idx + len(end) > idx and (
                '"keyfacts"' in end or '"fullTitle"' in end or '"title"' in end
            ):
                blob = end
                break
            search_pos = brace_idx

        if blob:
            try:
                parsed = json.loads(blob)
                keyfacts = parsed.get("keyfacts", {})
                price = parsed.get("price", {})
                title = (
                    keyfacts.get("fullTitle") or keyfacts.get("title")
                    or parsed.get("fullTitle") or parsed.get("title")
                )
                if title and price.get("price") is not None:
                    products.append({
                        "title": title,
                        "price": price["price"],
                        "old_price": price.get("oldPrice"),
                    })
            except Exception:
                pass

        pos = idx + len(needle)

    return products, resp.text


# Gramatura/objętość opakowania NIE jest ujawniana w polach JSON, które
# widzieliśmy w SSR (patrz probe_endpoints.py) — ale polskie nazwy
# produktów spożywczych zwyczajowo zawierają ją wprost w tytule
# (np. "Cukier biały 1 kg", "Mleko 3,2% 1l", "Jajka 10 szt"). Bez tego nie
# da się BEZPIECZNIE przeliczyć ceny opakowania na cenę za 100g/ml —
# zgadywanie stałej gramatury odtworzyłoby dokładnie ten sam błąd
# (absurdalne ceny), który naprawiliśmy wcześniej w tej sesji. Więc:
# znajdź gramaturę/ilość w tytule albo pomiń produkt, nigdy nie zgaduj.
GRAMMAGE_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b', re.IGNORECASE)
COUNT_PATTERN = re.compile(r'(\d{1,2})\s*szt\b', re.IGNORECASE)


def extract_unit_amount_grams(title: str, ingredient_name: str) -> float | None:
    """Zwraca gramaturę/objętość opakowania w gramach/ml (lub przeliczoną
    z liczby sztuk dla kategorii typu jajka), albo None jeśli tytuł nie
    zawiera żadnej wiarygodnej specyfikacji."""
    m = GRAMMAGE_PATTERN.search(title)
    if m:
        amount = float(m.group(1).replace(",", "."))
        unit = m.group(2).lower()
        if unit == "kg" or unit == "l":
            amount *= 1000
        return amount

    m = COUNT_PATTERN.search(title)
    if m:
        avg_weight = AVERAGE_UNIT_WEIGHT_G.get(ingredient_name)
        if avg_weight is not None:
            return float(m.group(1)) * avg_weight

    return None


class LidlScraper:
    store_name = "Lidl"
    store_website = "https://www.lidl.pl"

    def __init__(self):
        self.sb = get_supabase()
        self.store_id = get_or_create(
            self.sb, "stores", {"name": self.store_name},
            {"website_url": self.store_website, "is_active": True},
        )

    def scrape(self) -> dict:
        all_products: list[dict] = []

        root_products, root_html = extract_products_from_category(ROOT_GROCERY_URL)
        print(f"[Lidl] {ROOT_GROCERY_URL} -> {len(root_products)} produktów osadzonych w SSR")
        all_products.extend(root_products)

        subcategory_urls = discover_grocery_subcategories(root_html)
        print(f"[Lidl] Znaleziono {len(subcategory_urls)} podkategorii spożywczych do sprawdzenia")

        for url in subcategory_urls:
            products, _ = extract_products_from_category(url)
            print(f"[Lidl] {url} -> {len(products)} produktów osadzonych w SSR")
            all_products.extend(products)

        if DEBUG:
            print(f"[Lidl] Wszystkie tytuły produktów znalezione ({len(all_products)}):")
            for p in all_products:
                print(f"[Lidl]   tytuł: {p['title']!r} ({p['price']} zł)")

        found_per_ingredient: dict[str, dict] = {}
        for p in all_products:
            ingredient_name = match_ingredient(p["title"])
            if not ingredient_name:
                continue
            print(f"[Lidl] Dopasowano '{p['title']}' -> {ingredient_name} ({p['price']} zł)")
            if ingredient_name not in found_per_ingredient or p["price"] < found_per_ingredient[ingredient_name]["price"]:
                found_per_ingredient[ingredient_name] = p

        saved = self._save(found_per_ingredient)
        return {"products_seen": len(all_products), "ingredients_found": len(found_per_ingredient), "saved": saved}

    def _save(self, found_per_ingredient: dict[str, dict]) -> int:
        if not found_per_ingredient:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        valid_to = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        saved = 0

        for ingredient_name, p in found_per_ingredient.items():
            unit_amount = extract_unit_amount_grams(p["title"], ingredient_name)
            if unit_amount is None:
                print(f"[Lidl] Pomijam '{p['title']}' — nie znaleziono gramatury/ilości w nazwie, "
                      f"nie da się bezpiecznie policzyć ceny za 100g/ml")
                continue

            price_per_100 = round(p["price"] / (unit_amount / 100.0), 4)
            if not is_plausible(ingredient_name, price_per_100):
                print(f"[Lidl] Odrzucam nieprawdopodobną cenę: {ingredient_name} -> "
                      f"{price_per_100} zł/100 (z '{p['title']}', {p['price']} zł za {unit_amount:g}g)")
                continue

            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = f"{p['title']} (Lidl)"
            store_product_id = get_or_create(
                self.sb, "store_products",
                {"store_id": self.store_id, "name": product_name},
                {"unit": "g", "unit_amount": unit_amount},
            )

            self.sb.table("prices").insert({
                "store_product_id": store_product_id,
                "gross_price": p["price"],
                "source": "flyer-ssr",
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
                    "priority": 20,
                }).execute()

            saved += 1

        return saved


if __name__ == "__main__":
    result = LidlScraper().scrape()
    print(f"\n[Lidl] Podsumowanie: {result}")
