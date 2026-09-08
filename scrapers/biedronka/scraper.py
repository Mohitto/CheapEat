"""
Scraper gazetki Biedronka — realny pipeline oparty na OCR.

Biedronka NIE udostępnia strukturalnych danych cenowych (sprawdzone
dokładnie przez scrapers/probe_biedronka_*.py — leaflet-api zwraca tylko
bitmapy stron, zero hotspotów/cen jako dane). Jedyna droga do prawdziwych
cen to:

  1. https://www.biedronka.pl/pl/gazetki -> link do aktualnej gazetki
     (press,id,...), preferując wariant "codziennie-niskie-ceny"
  2. Strona press,id,... zawiera w statycznym HTML:
     window.galleryLeaflet.init("{UUID}")
  3. https://leaflet-api.prod.biedronka.cloud/api/leaflets/{UUID}?ctx=web
     zwraca images_desktop: [{page, images: [url PNG]}]
  4. Tesseract OCR (darmowy, open-source — projekt ma być bezpłatny, więc
     celowo nie płatne API wizyjne) na każdej stronie, --psm 3 -l pol
  5. Dwa rodzaje wzorców cenowych (patrz extract_price_candidates):
     a) jawna cena za jednostkę: "X,XX zł/100 g", "/100 ml", "/kg", "/l"
     b) cena za opakowanie: "X,XX zł" + gramatura/ilość znaleziona w
        pobliskim tekście ("500 g", "10 szt"...) — obejmuje produkty
        typu "500g mięsa mielonego — 5,49 zł" albo "10 szt jajek — 9,89 zł",
        które NIE są podane jako cena za 100g wprost.
  Klasyfikacja do kategorii składnika (jajka, mięso mielone, ...) jest
  markowo-agnostyczna — patrz scrapers/ingredient_catalog.py (współdzielony
  z lidl/scraper.py, żeby oba sklepy klasyfikowały identycznie).

Bezpieczeństwo: każdy kandydat musi przejść ingredient_catalog.is_plausible
(rozsądny zakres zł/100g dla danej kategorii) zanim trafi do bazy — OCR na
stylizowanej grafice marketingowej regularnie się myli, a to samo dotyczy
dopasowania kontekstu (cena sąsiedniego produktu w oknie). Lepiej brakująca
cena niż pewna siebie zła cena.
"""
import os
import re
import subprocess
import sys
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

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
PRESS_LINK_PATTERN = re.compile(r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\']+)["\']')
UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')

# 1) Jawna cena za jednostkę — nic do przeliczenia poza jednostką bazową.
EXPLICIT_UNIT_PRICE_PATTERNS = [
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*100\s*g', re.IGNORECASE), "100g", 1.0),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*100\s*ml', re.IGNORECASE), "100ml", 1.0),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*kg', re.IGNORECASE), "kg", 0.1),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*l\b', re.IGNORECASE), "l", 0.1),
]

# 2) Zwykła cena (nie zaraz po niej "/coś" — to by już złapał wzór powyżej).
PACKAGE_PRICE_PATTERN = re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl](?!\s*/)', re.IGNORECASE)

# Specyfikacje wagi/ilości opakowania szukane w pobliżu ceny z (2).
PACKAGE_SPEC_PATTERNS = [
    (re.compile(r'\b(\d{2,4})\s*g\b', re.IGNORECASE), "g", 1.0),
    (re.compile(r'\b(\d+(?:[,.]\d+)?)\s*kg\b', re.IGNORECASE), "kg", 1000.0),
    (re.compile(r'\b(\d{2,4})\s*ml\b', re.IGNORECASE), "ml", 1.0),
    (re.compile(r'\b(\d{1,2})\s*szt\b', re.IGNORECASE), "szt", None),  # None = licz sztuki, nie gramy
]

CONTEXT_WINDOW_CHARS = 200
PACKAGE_SPEC_WINDOW_CHARS = 150


def get_or_create(sb, table: str, match: dict, defaults: dict | None = None) -> str:
    query = sb.table(table).select("id")
    for key, value in match.items():
        query = query.eq(key, value)
    res = query.limit(1).execute()
    if res.data:
        return res.data[0]["id"]
    ins = sb.table(table).insert({**match, **(defaults or {})}).execute()
    return ins.data[0]["id"]


def find_current_press_url() -> str:
    resp = requests.get(GAZETKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    candidates = sorted(set(PRESS_LINK_PATTERN.findall(resp.text)))
    if not candidates:
        raise RuntimeError("Nie znaleziono linku do aktualnej gazetki na /pl/gazetki")
    chosen = next((c for c in candidates if "codziennie-niskie-ceny" in c), candidates[0])
    return "https://www.biedronka.pl" + chosen


def find_uuid(press_url: str) -> str:
    resp = requests.get(press_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    m = UUID_PATTERN.search(resp.text)
    if not m:
        raise RuntimeError("Nie znaleziono window.galleryLeaflet.init(...) w HTML strony press")
    return m.group(1)


def get_page_image_urls(uuid: str) -> list[str]:
    api_url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Niektóre strony (np. okładka) mają pustą pierwszą pozycję w "images" —
    # bierzemy pierwszy NIEPUSTY URL, nie zakładamy że images[0] nim jest.
    urls = []
    for p in data["images_desktop"]:
        for img_url in p.get("images", []):
            if img_url:
                urls.append(img_url)
                break
    return urls


def ocr_page(image_url: str) -> str:
    img_resp = requests.get(image_url, headers=HEADERS, timeout=30)
    img_resp.raise_for_status()
    tmp_path = "/tmp/biedronka_page.png"
    with open(tmp_path, "wb") as f:
        f.write(img_resp.content)
    # Bez timeoutu tesseract potrafił wisieć w nieskończoność na
    # niektórych stronach (zablokował cały workflow na >6h limicie joba,
    # zamiast pominąć jedną stronę jak przy błędzie sieci — patrz
    # obsługa wyjątków w scrape()).
    result = subprocess.run(
        ["tesseract", tmp_path, "stdout", "-l", "pol", "--psm", "3"],
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout


def _nearest_package_spec(text: str, price_pos: int) -> tuple[float | None, str | None, int | None]:
    """Szuka specyfikacji wagi/ilości opakowania (500 g / 1 kg / 10 szt) w
    oknie wokół pozycji ceny (przed i po) i zwraca tę najbliższą pozycyjnie.
    Zwraca (ilość_surowa, jednostka, odległość_w_znakach) albo (None, None, None)."""
    window_start = max(0, price_pos - PACKAGE_SPEC_WINDOW_CHARS)
    window_end = min(len(text), price_pos + PACKAGE_SPEC_WINDOW_CHARS)
    window = text[window_start:window_end]
    price_pos_in_window = price_pos - window_start

    best = (None, None, None)
    best_distance = None
    for pattern, unit_label, _ in PACKAGE_SPEC_PATTERNS:
        for m in pattern.finditer(window):
            distance = min(abs(m.start() - price_pos_in_window), abs(m.end() - price_pos_in_window))
            if best_distance is None or distance < best_distance:
                raw_amount = float(m.group(1).replace(",", "."))
                best = (raw_amount, unit_label, distance)
                best_distance = distance
    return best


def extract_price_candidates(text: str) -> list[dict]:
    """Zwraca listę {ingredient_name, price_per_100_units, raw_price, raw_unit}
    dla każdego rozpoznanego i wiarygodnego dopasowania."""
    candidates = []

    # --- 1) Jawna cena za jednostkę ---
    for pattern, unit_label, to_100_factor in EXPLICIT_UNIT_PRICE_PATTERNS:
        for m in pattern.finditer(text):
            raw_price = float(m.group(1).replace(",", "."))
            price_per_100 = round(raw_price * to_100_factor, 4)

            window_start = max(0, m.start() - CONTEXT_WINDOW_CHARS)
            context = text[window_start:m.start()]
            ingredient_name = match_ingredient(context)
            if not ingredient_name:
                continue

            if not is_plausible(ingredient_name, price_per_100):
                print(f"[Biedronka] Odrzucam nieprawdopodobną cenę: {ingredient_name} "
                      f"-> {price_per_100} zł/100 (surowo: {raw_price} zł/{unit_label})")
                continue

            candidates.append({
                "ingredient_name": ingredient_name,
                "price_per_100_units": price_per_100,
                "raw_price": raw_price,
                "raw_unit": unit_label,
            })

    # --- 2) Cena za opakowanie + znaleziona w pobliżu gramatura/ilość ---
    for m in PACKAGE_PRICE_PATTERN.finditer(text):
        raw_price = float(m.group(1).replace(",", "."))

        context_start = max(0, m.start() - CONTEXT_WINDOW_CHARS)
        context = text[context_start:m.start()]
        ingredient_name = match_ingredient(context)
        if not ingredient_name:
            continue

        raw_amount, unit_label, _ = _nearest_package_spec(text, m.start())
        if raw_amount is None:
            continue  # bez wiarygodnej gramatury/ilości nie zgadujemy

        if unit_label == "szt":
            avg_weight = AVERAGE_UNIT_WEIGHT_G.get(ingredient_name)
            if avg_weight is None:
                continue  # nie znamy średniej wagi sztuki dla tej kategorii
            unit_amount_g = raw_amount * avg_weight
        elif unit_label == "kg":
            unit_amount_g = raw_amount * 1000.0
        else:  # "g" lub "ml" — już w jednostce bazowej
            unit_amount_g = raw_amount

        if unit_amount_g <= 0:
            continue

        price_per_100 = round(raw_price / (unit_amount_g / 100.0), 4)

        if not is_plausible(ingredient_name, price_per_100):
            print(f"[Biedronka] Odrzucam nieprawdopodobną cenę (opakowanie): {ingredient_name} "
                  f"-> {price_per_100} zł/100 (surowo: {raw_price} zł za {raw_amount} {unit_label})")
            continue

        candidates.append({
            "ingredient_name": ingredient_name,
            "price_per_100_units": price_per_100,
            "raw_price": raw_price,
            "raw_unit": f"{raw_amount:g}{unit_label}",
        })

    return candidates


class BiedronkaScraper:
    store_name = "Biedronka"
    store_website = "https://www.biedronka.pl"

    def __init__(self):
        self.sb = get_supabase()
        self.store_id = get_or_create(
            self.sb, "stores", {"name": self.store_name},
            {"website_url": self.store_website, "is_active": True},
        )

    def scrape(self) -> dict:
        press_url = find_current_press_url()
        print(f"[Biedronka] Aktualna gazetka: {press_url}")
        uuid = find_uuid(press_url)
        print(f"[Biedronka] UUID: {uuid}")
        image_urls = get_page_image_urls(uuid)
        print(f"[Biedronka] Stron do przetworzenia: {len(image_urls)}")

        found_per_ingredient: dict[str, dict] = {}
        keyword_seen_on_page: dict[str, int] = {}

        for i, image_url in enumerate(image_urls):
            if DEBUG:
                print(f"[Biedronka] Strona {i}/{len(image_urls)}: pobieram i OCR-uję...")
            try:
                text = ocr_page(image_url)
            except Exception as e:
                print(f"[Biedronka] Strona {i}: błąd OCR ({e}), pomijam")
                continue

            if DEBUG:
                text_lower = text.lower()
                for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
                    if ingredient_name in keyword_seen_on_page:
                        continue
                    for kw in keywords:
                        idx = text_lower.find(kw)
                        if idx != -1:
                            snippet = text[max(0, idx - 40):idx + 60].replace("\n", " ")
                            keyword_seen_on_page[ingredient_name] = i
                            print(f"[Biedronka] Strona {i}: '{kw}' (kategoria: {ingredient_name}) w OCR -> "
                                  f"...{snippet}...")
                            break

            candidates = extract_price_candidates(text)
            for c in candidates:
                name = c["ingredient_name"]
                # Jeśli kilka stron trafia w ten sam składnik, zostaw najtańszą
                # (typowe zachowanie promocji — najniższa widoczna cena wygrywa).
                if name not in found_per_ingredient or c["price_per_100_units"] < found_per_ingredient[name]["price_per_100_units"]:
                    found_per_ingredient[name] = c
                    print(f"[Biedronka] Strona {i}: {name} -> {c['price_per_100_units']} zł/100 "
                          f"(surowo: {c['raw_price']} zł/{c['raw_unit']})")

        if DEBUG:
            missing = [name for name in INGREDIENT_KEYWORDS if name not in found_per_ingredient]
            print(f"[Biedronka] Kategorie bez ceny w tej gazetce: {missing}")
            print(f"[Biedronka] Kategorie których słowo kluczowe w ogóle NIE pojawiło się w OCR "
                  f"(prawdopodobnie brak promocji w tym tygodniu): "
                  f"{[m for m in missing if m not in keyword_seen_on_page]}")
            print(f"[Biedronka] Kategorie których słowo kluczowe pojawiło się, ale nie wyszła cena "
                  f"(warto zbadać ekstrakcję): {[m for m in missing if m in keyword_seen_on_page]}")

        saved = self._save(found_per_ingredient)
        return {"pages_scanned": len(image_urls), "ingredients_found": len(found_per_ingredient), "saved": saved}

    def _save(self, found_per_ingredient: dict[str, dict]) -> int:
        if not found_per_ingredient:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        valid_to = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        saved = 0

        for ingredient_name, c in found_per_ingredient.items():
            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = f"{ingredient_name.capitalize()} Biedronka (gazetka)"
            store_product_id = get_or_create(
                self.sb, "store_products",
                {"store_id": self.store_id, "name": product_name},
                {"unit": "g", "unit_amount": 100},
            )

            self.sb.table("prices").insert({
                "store_product_id": store_product_id,
                "gross_price": c["price_per_100_units"],
                "source": "flyer-ocr",
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
                    "conversion_factor": 1.0,
                    "priority": 5,
                }).execute()

            saved += 1

        return saved


if __name__ == "__main__":
    result = BiedronkaScraper().scrape()
    print(f"\n[Biedronka] Podsumowanie: {result}")
