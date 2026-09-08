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
import gzip
import html as html_module
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_supabase
from ingredient_catalog import (
    AVERAGE_UNIT_WEIGHT_G,
    INGREDIENT_DEFAULTS,
    INGREDIENT_KEYWORDS,
    is_plausible,
    match_ingredient,
)

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

# Sprawdzone na żywo: link nav na stronie /c/zywnosc-i-napoje/... to
# globalne menu CAŁEGO sklepu (moda, ogród, dom...), nie zagnieżdżone
# podkategorie spożywcze — SSR HTML tej strony ich po prostu nie zawiera.
# Sitemap to osobne, publicznie opublikowane źródło prawdziwych URL-i;
# robots.txt to standardowy (sitemaps.org), nie zgadywany sposób na
# znalezienie jego adresu.
ROBOTS_URL = "https://www.lidl.pl/robots.txt"
SITEMAP_DIRECTIVE_PATTERN = re.compile(r'^Sitemap:\s*(\S+)', re.IGNORECASE | re.MULTILINE)
SITEMAP_LOC_PATTERN = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>', re.IGNORECASE)
CATEGORY_URL_PATTERN = re.compile(r'/c/[a-z0-9-]+/s\d+', re.IGNORECASE)
MAX_NESTED_SITEMAPS = 5

# Sprawdzone na żywo: sitemap "pages" ogłoszony w tym samym indeksie to
# strony poradnikowe/CMS (np. "jajka-wielkanocne...-poradnik"), NIE
# kategorie sklepowe — mimo że pasują do wzorca /c/.../sNNN, dają 0
# produktów. Prawdziwa wartość jest w product_sitemap.xml.gz: 9000+
# realnych stron PRODUKTOWYCH (/p/<opisowy-slug>/pNNNNN) z nazwą produktu
# wprost w URL-u — więc zamiast zgadywać, które kategorie zawierają nasze
# składniki, dopasowujemy słowa kluczowe bezpośrednio do sluga i odwiedzamy
# tylko te konkretne strony produktowe.
PRODUCT_SITEMAP_NAME_HINT = "product_sitemap"
MAX_PRODUCT_MATCHES_PER_INGREDIENT = 3
_POLISH_FOLD = str.maketrans({"ł": "l", "Ł": "L"})


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


def discover_promotions_page(html: str) -> str | None:
    """Link do strony "Promocje" (bieżące oferty całego sklepu) —
    prawdziwy, odkryty w tej samej nawigacji co podkategorie, a nie
    numer strony wpisany na sztywno (mógłby się kiedyś zmienić)."""
    links = set(SUBCATEGORY_LINK_PATTERN.findall(html))
    for l in sorted(links):
        if "/c/promocje/" in l.lower():
            return "https://www.lidl.pl" + l
    return None


def _fetch_sitemap_locs(url: str) -> list[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"[Lidl] Nie udało się pobrać {url}: {e}")
        return []
    if resp.status_code != 200:
        print(f"[Lidl] {url} -> status {resp.status_code}")
        return []
    # .xml.gz to skompresowany plik (nie HTTP Content-Encoding) — trzeba
    # ręcznie zdekompresować, inaczej regex nie znajdzie nic w binarnych
    # bajtach gzip. To dokładnie ta pułapka, w którą wcześniej wpadliśmy:
    # nasz filtr zagnieżdżonych sitemap sprawdzał tylko końcówkę ".xml" i
    # cicho pomijał oba prawdziwe kandydaty (product_sitemap.xml.gz,
    # pages_pl-PL_pl.xml.gz), zostawiając tylko nieistotny sitemap sklepów.
    if url.lower().endswith(".gz"):
        try:
            text = gzip.decompress(resp.content).decode("utf-8", errors="replace")
        except OSError as e:
            print(f"[Lidl] Nie udało się zdekompresować {url}: {e}")
            return []
    else:
        text = resp.text
    return SITEMAP_LOC_PATTERN.findall(text)


def get_product_sitemap_urls() -> list[str]:
    """Zwraca wszystkie prawdziwe adresy stron produktowych z
    product_sitemap.xml.gz, ogłoszonego w robots.txt (standard
    sitemaps.org — nie zgadujemy jego adresu) -> static/sitemap.xml."""
    try:
        robots_resp = requests.get(ROBOTS_URL, headers=HEADERS, timeout=30)
        sitemap_urls = SITEMAP_DIRECTIVE_PATTERN.findall(robots_resp.text) if robots_resp.status_code == 200 else []
    except requests.RequestException as e:
        print(f"[Lidl] Nie udało się pobrać robots.txt: {e}")
        sitemap_urls = []
    if DEBUG:
        print(f"[Lidl] robots.txt wskazuje {len(sitemap_urls)} sitemap(y): {sitemap_urls}")

    for sitemap_url in sitemap_urls:
        for nested_url in _fetch_sitemap_locs(sitemap_url)[:MAX_NESTED_SITEMAPS]:
            if PRODUCT_SITEMAP_NAME_HINT in nested_url.lower():
                product_urls = _fetch_sitemap_locs(nested_url)
                if DEBUG:
                    print(f"[Lidl] {nested_url}: {len(product_urls)} adresów stron produktowych")
                return product_urls
    return []


def _normalize_for_slug_match(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower())


def _slugify_keyword(kw: str) -> str:
    """Prawdziwe URL-e Lidla są już czysto ASCII (np. "górski" -> "gorski"
    w sitemapie), ale nasze polskie słowa kluczowe (np. "mięso mielone")
    nie są — trzeba je najpierw ręcznie przetransliterować (ł/Ł nie
    dekomponuje się przez NFKD, to osobna litera, nie litera+akcent) i
    dopiero potem znormalizować spacje/myślniki tak samo jak URL-e."""
    folded = kw.translate(_POLISH_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _normalize_for_slug_match(ascii_only)


def match_product_urls_by_slug(product_urls: list[str]) -> dict[str, list[str]]:
    """Dopasowuje słowa kluczowe składników bezpośrednio do sluga
    prawdziwych stron produktowych (np. "jajka" -> ".../jajka-wiejskie-
    .../pNNNNN") zamiast zgadywać, w której kategorii szukać. Wymaga
    dopasowania na granicy "słowa" (otoczonego myślnikami po normalizacji),
    żeby np. "ryż" nie złapał przypadkiem środka jakiegoś dłuższego sluga."""
    normalized_urls = {u: f"-{_normalize_for_slug_match(u)}-" for u in product_urls}
    matches: dict[str, list[str]] = {}

    for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
        slug_keywords = [f"-{_slugify_keyword(kw)}-" for kw in keywords]
        found = [u for u, norm in normalized_urls.items() if any(skw in norm for skw in slug_keywords)]
        if found:
            matches[ingredient_name] = found[:MAX_PRODUCT_MATCHES_PER_INGREDIENT]

    return matches


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
        promo_url = discover_promotions_page(root_html)
        if promo_url and promo_url not in subcategory_urls:
            subcategory_urls.append(promo_url)
        print(f"[Lidl] Znaleziono {len(subcategory_urls)} podkategorii/stron spożywczych do sprawdzenia")

        for url in subcategory_urls:
            products, _ = extract_products_from_category(url)
            print(f"[Lidl] {url} -> {len(products)} produktów osadzonych w SSR")
            all_products.extend(products)

        # Nawigacja i strony CMS nie ujawniają prawdziwych podkategorii
        # spożywczych (sprawdzone na żywo — patrz komentarz przy
        # PRODUCT_SITEMAP_NAME_HINT) — zamiast tego dopasuj słowa kluczowe
        # bezpośrednio do slugów 9000+ prawdziwych stron produktowych.
        product_urls = get_product_sitemap_urls()
        slug_matches = match_product_urls_by_slug(product_urls)
        if DEBUG:
            print(f"[Lidl] Dopasowania po slugu URL ({len(product_urls)} stron w sitemapie): "
                  f"{ {k: len(v) for k, v in slug_matches.items()} }")
        for ingredient_name, urls in slug_matches.items():
            for url in urls:
                products, _ = extract_products_from_category(url)
                print(f"[Lidl] (slug: {ingredient_name}) {url} -> {len(products)} produktów osadzonych w SSR")
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
