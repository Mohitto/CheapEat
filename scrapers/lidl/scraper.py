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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

# Kategorie spożywcze potwierdzone/prawdopodobne na lidl.pl. Tylko pierwsza
# jest zweryfikowana na żywo (patrz docstring); reszta to te same wzorce
# URL co lidl.pl używa dla innych działów spożywczych — jeśli któraś nie
# istnieje, po prostu zwróci 404 i zostanie pominięta.
GROCERY_CATEGORY_URLS = [
    "https://www.lidl.pl/c/zywnosc-i-napoje/s10068374",
]

# Nazwa naszego składnika -> słowa kluczowe szukane w tytule produktu.
# Ta sama filozofia co w biedronka/scraper.py: lista mała i stała, proste
# dopasowanie podciągu zamiast fuzzy matching.
INGREDIENT_KEYWORDS: dict[str, list[str]] = {
    "mąka pszenna": ["mąka pszenna", "mąka"],
    "cukier": ["cukier"],
    "masło": ["masło"],
    "ryż": ["ryż"],
    "kurczak pierś": ["pierś z kurczaka", "filet z kurczaka", "kurczak"],
    "cebula": ["cebula"],
    "pomidor": ["pomidor"],
    "ser żółty": ["ser żółty", "ser gouda", "ser edamski"],
    "olej rzepakowy": ["olej rzepakowy", "olej"],
    "sól": ["sól"],
    "mleko": ["mleko"],
    "jajka": ["jajka", "jaja"],
}


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


def extract_products_from_category(url: str) -> list[dict]:
    """Zwraca listę {title, price, old_price} z produktów osadzonych w SSR
    HTML strony kategorii (patrz docstring modułu — nie wszystkie produkty
    z kategorii tu będą, tylko te które Lidl osadza server-side)."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[Lidl] {url} -> status {resp.status_code}, pomijam")
        return []

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

    return products


def match_ingredient(title: str) -> str | None:
    title_lower = title.lower()
    for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return ingredient_name
    return None


# Gramatura/objętość opakowania NIE jest ujawniana w polach JSON, które
# widzieliśmy w SSR (patrz probe_endpoints.py) — ale polskie nazwy
# produktów spożywczych zwyczajowo zawierają ją wprost w tytule
# (np. "Cukier biały 1 kg", "Mleko 3,2% 1l"). Bez tego nie da się
# BEZPIECZNIE przeliczyć ceny opakowania na cenę za 100g/ml — zgadywanie
# stałej gramatury odtworzyłoby dokładnie ten sam błąd (absurdalne ceny),
# który naprawiliśmy wcześniej w tej sesji. Więc: znajdź gramaturę w
# tytule albo pomiń produkt, nigdy nie zgaduj.
GRAMMAGE_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b', re.IGNORECASE
)


def extract_unit_amount_grams(title: str) -> float | None:
    """Zwraca gramaturę/objętość opakowania w gramach/ml, albo None jeśli
    tytuł jej nie zawiera (w takim przypadku produkt trzeba pominąć)."""
    m = GRAMMAGE_PATTERN.search(title)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit == "kg" or unit == "l":
        amount *= 1000
    return amount


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
        all_products = []
        for url in GROCERY_CATEGORY_URLS:
            products = extract_products_from_category(url)
            print(f"[Lidl] {url} -> {len(products)} produktów osadzonych w SSR")
            all_products.extend(products)

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
            # Cena produktu Lidl to cena CAŁEGO opakowania, nie per-100g —
            # w przeciwieństwie do Biedronki, gdzie gazetka podaje wprost
            # zł/100g. Bez prawdziwej gramatury nie wolno zgadywać stałej
            # (to odtworzyłoby dokładnie ten sam błąd absurdalnych cen,
            # który naprawiliśmy wcześniej w tej sesji) — więc parsujemy
            # gramaturę z tytułu produktu i POMIJAMY, jeśli jej tam nie ma.
            unit_amount = extract_unit_amount_grams(p["title"])
            if unit_amount is None:
                print(f"[Lidl] Pomijam '{p['title']}' — nie znaleziono gramatury/objętości w nazwie, "
                      f"nie da się bezpiecznie policzyć ceny za 100g/ml")
                continue

            ing_res = self.sb.table("ingredients").select("id").eq("name", ingredient_name).limit(1).execute()
            if not ing_res.data:
                print(f"[Lidl] Pomijam '{ingredient_name}' — nie ma go w tabeli ingredients")
                continue
            ingredient_id = ing_res.data[0]["id"]

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
