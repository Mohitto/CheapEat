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
  5. Regex na wzorce cenowe "X,XX zł/100 g" / "zł/100 ml" / "zł/kg" / "zł/l"
     + dopasowanie nazwy produktu (tekst tuż przed ceną) do znanych
     składników przez proste dopasowanie słów kluczowych

Ograniczenia świadomie przyjęte w V1:
- Tylko produkty z ceną podaną za wagę/objętość (zł/100g, zł/kg, zł/l) —
  ceny za sztukę (zł/szt) pomijamy, bo nasze składniki poza jajkami są
  wagowe, a jajka i tak nie mają w gazetce ceny per-100g.
- OCR bywa niedokładny na stronach typu "hero/okładka" — strony bez
  rozpoznanej ceny są po prostu pomijane, nie ma tam nic do zepsucia.
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_supabase

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
PRESS_LINK_PATTERN = re.compile(r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\']+)["\']')
UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')

# Wzorce cen za wagę/objętość. Grupa 1 = liczba (przecinek lub kropka),
# grupa 2 = jednostka bazowa użyta w gazetce.
PRICE_PATTERNS = [
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*100\s*g', re.IGNORECASE), "100g", 1.0),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*100\s*ml', re.IGNORECASE), "100ml", 1.0),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*kg', re.IGNORECASE), "kg", 0.1),
    (re.compile(r'(\d{1,3}[,.]\d{2})\s*z[łl]\s*/\s*l\b', re.IGNORECASE), "l", 0.1),
]

# Nazwa naszego składnika -> słowa kluczowe szukane w tekście OCR wokół ceny.
# Lista celowo mała i dosłowna (nie fuzzy matching) — nasz zestaw składników
# jest mały i stały (patrz seed_dev_data.py), więc proste dopasowanie
# podciągu jest wystarczające i dużo bardziej przewidywalne niż fuzzy.
INGREDIENT_KEYWORDS: dict[str, list[str]] = {
    "mąka pszenna": ["mąka pszenna", "mąka"],
    "cukier": ["cukier"],
    "masło": ["masło"],
    "ryż": ["ryż"],
    "kurczak pierś": ["pierś z kurczaka", "filet z kurczaka", "kurczak"],
    "cebula": ["cebula"],
    "pomidor": ["pomidor"],
    "ser żółty": ["ser żółty", "ser gouda", "ser edamski", "ser salami"],
    "olej rzepakowy": ["olej rzepakowy", "olej"],
    "sól": ["sól"],
    "mleko": ["mleko"],
}

CONTEXT_WINDOW_CHARS = 200


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
    return [p["images"][0] for p in data["images_desktop"] if p["images"]]


def ocr_page(image_url: str) -> str:
    img_resp = requests.get(image_url, headers=HEADERS, timeout=30)
    img_resp.raise_for_status()
    tmp_path = "/tmp/biedronka_page.png"
    with open(tmp_path, "wb") as f:
        f.write(img_resp.content)
    result = subprocess.run(
        ["tesseract", tmp_path, "stdout", "-l", "pol", "--psm", "3"],
        capture_output=True, text=True,
    )
    return result.stdout


def extract_price_candidates(text: str) -> list[dict]:
    """Zwraca listę {ingredient_name, price_per_100_units, raw_price, raw_unit}
    dla każdego rozpoznanego dopasowania (cena + nazwa składnika w pobliżu)."""
    candidates = []
    for pattern, unit_label, to_100_factor in PRICE_PATTERNS:
        for m in pattern.finditer(text):
            raw_price = float(m.group(1).replace(",", "."))
            price_per_100 = round(raw_price * to_100_factor, 4)

            window_start = max(0, m.start() - CONTEXT_WINDOW_CHARS)
            context = text[window_start:m.start()].lower()

            for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
                if any(kw in context for kw in keywords):
                    candidates.append({
                        "ingredient_name": ingredient_name,
                        "price_per_100_units": price_per_100,
                        "raw_price": raw_price,
                        "raw_unit": unit_label,
                    })
                    break
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

        for i, image_url in enumerate(image_urls):
            try:
                text = ocr_page(image_url)
            except Exception as e:
                print(f"[Biedronka] Strona {i}: błąd OCR ({e}), pomijam")
                continue

            candidates = extract_price_candidates(text)
            for c in candidates:
                name = c["ingredient_name"]
                # Jeśli kilka stron trafia w ten sam składnik, zostaw najtańszą
                # (typowe zachowanie promocji — najniższa widoczna cena wygrywa).
                if name not in found_per_ingredient or c["price_per_100_units"] < found_per_ingredient[name]["price_per_100_units"]:
                    found_per_ingredient[name] = c
                    print(f"[Biedronka] Strona {i}: {name} -> {c['price_per_100_units']} zł/100 "
                          f"(surowo: {c['raw_price']} zł/{c['raw_unit']})")

        saved = self._save(found_per_ingredient)
        return {"pages_scanned": len(image_urls), "ingredients_found": len(found_per_ingredient), "saved": saved}

    def _save(self, found_per_ingredient: dict[str, dict]) -> int:
        if not found_per_ingredient:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        valid_to = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        saved = 0

        for ingredient_name, c in found_per_ingredient.items():
            ing_res = self.sb.table("ingredients").select("id").eq("name", ingredient_name).limit(1).execute()
            if not ing_res.data:
                print(f"[Biedronka] Pomijam '{ingredient_name}' — nie ma go w tabeli ingredients")
                continue
            ingredient_id = ing_res.data[0]["id"]

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
