"""
Scraper gazetki Biedronka — ceny promocyjne odczytywane z obrazków.

Biedronka NIE udostępnia cen gazetkowych jako danych (sprawdzone przez
scrapers/probe_biedronka_*.py — leaflet-api zwraca wyłącznie bitmapy
stron). Jedyna droga to OCR, i to on jest rdzeniem cen promocyjnych w tej
aplikacji:

  1. biedronka/flyers.py — WSZYSTKIE gazetki z /pl/gazetki wraz z okresem
     obowiązywania (data startu jest w slugu adresu). Czytamy tylko te
     obowiązujące dzisiaj, więc wydanie zapowiedziane na przyszły tydzień
     nie zaniża cen, a wygasłe znikają same.
  2. Strona press,id,... zawiera window.galleryLeaflet.init("{UUID}"),
     a leaflet-api pod tym UUID-em zwraca adresy obrazków stron.
  3. biedronka/leaflet_ocr.py — tesseract (darmowy, open-source: projekt
     ma pozostać bezpłatny, więc świadomie bez płatnych API wizyjnych) w
     trybie TSV, czyli ze współrzędnymi każdego słowa. Cenę wiążemy z
     nazwą produktu i gramaturą po ODLEGŁOŚCI NA STRONIE, bo gazetka to
     siatka kafelków i kolejność czytania tekstu nie odpowiada układowi.

Klasyfikacja do kategorii składnika jest markowo-agnostyczna i wspólna z
pozostałymi sklepami — patrz scrapers/ingredient_catalog.py.

Bezpieczeństwo: każdy kandydat musi przejść ingredient_catalog.is_plausible
(rozsądny zakres ceny jednostkowej dla kategorii), zanim trafi do bazy —
OCR na stylizowanej grafice marketingowej regularnie się myli. Lepiej
brakująca cena niż pewna siebie zła cena.
"""
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_or_create, get_supabase, replace_price
from ingredient_catalog import INGREDIENT_DEFAULTS, INGREDIENT_KEYWORDS

from .flyers import active_flyers
from .leaflet_ocr import extract_candidates, ocr_page

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')

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
        """Czyta WSZYSTKIE gazetki obowiązujące dzisiaj.

        Wcześniej brana była jedna gazetka wybrana po nazwie, przez co
        (a) trafialiśmy w wydanie zaczynające się dopiero za kilka dni,
        czyli w ceny jeszcze nieobowiązujące, i (b) w ogóle nie
        otwieraliśmy gazetek tematycznych ("festiwal nabiału"), gdzie
        siedzi część promocji na nasze składniki."""
        flyers = active_flyers()
        if not flyers:
            print("[Biedronka] Brak gazetek obowiązujących dzisiaj")
            return {"flyers": 0, "pages_scanned": 0, "ingredients_found": 0, "saved": 0}

        print(f"[Biedronka] Gazetki obowiązujące dzisiaj: {len(flyers)}")
        for f in flyers:
            print(f"[Biedronka]   {f['slug']}: {f['valid_from']} .. {f['valid_to']}")

        found_per_ingredient: dict[str, dict] = {}
        pages_scanned = 0

        for flyer in flyers:
            try:
                uuid = find_uuid("https://www.biedronka.pl" + flyer["path"])
                image_urls = get_page_image_urls(uuid)
            except Exception as e:
                print(f"[Biedronka] {flyer['slug']}: nie udało się pobrać stron ({e}), pomijam")
                continue

            print(f"[Biedronka] {flyer['slug']}: {len(image_urls)} stron")

            for i, image_url in enumerate(image_urls):
                try:
                    tokens, page_width = ocr_page(image_url)
                except Exception as e:
                    print(f"[Biedronka] {flyer['slug']} strona {i}: błąd OCR ({e}), pomijam")
                    continue

                pages_scanned += 1
                for c in extract_candidates(tokens, page_width, debug=DEBUG):
                    name = c["ingredient_name"]
                    # Ten sam składnik potrafi być w kilku gazetkach naraz —
                    # zostaje najtańsza oferta, bo taką realnie się wybierze.
                    previous = found_per_ingredient.get(name)
                    if previous is None or c["unit_price"] < previous["unit_price"]:
                        found_per_ingredient[name] = {**c, "flyer": flyer}
                        print(f"[Biedronka] {flyer['slug']} s.{i}: {name} -> "
                              f"{c['package_price']} zł za {c['unit_amount']:g}{c['unit']} "
                              f"({round(c['unit_price'], 4)} zł/j.)")

        if DEBUG:
            missing = [n for n in INGREDIENT_KEYWORDS if n not in found_per_ingredient]
            print(f"[Biedronka] Kategorie bez ceny w gazetkach: {missing}")

        saved = self._save(found_per_ingredient)
        return {
            "flyers": len(flyers),
            "pages_scanned": pages_scanned,
            "ingredients_found": len(found_per_ingredient),
            "saved": saved,
        }

    def _save(self, found_per_ingredient: dict[str, dict]) -> int:
        if not found_per_ingredient:
            return 0

        saved = 0

        for ingredient_name, c in found_per_ingredient.items():
            unit, unit_amount = c["unit"], c["unit_amount"]
            # Ważność ceny bierzemy z gazetki, w której ją znaleźliśmy —
            # nie ze sztywnego "dziś + 3 dni". Dzięki temu promocja wygasa
            # dokładnie wtedy, kiedy kończy się gazetka, a apka wraca do
            # ceny regularnej ze sklepu.
            flyer = c["flyer"]
            valid_from = flyer["valid_from"].isoformat()
            valid_to = flyer["valid_to"].isoformat()

            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = f"{ingredient_name.capitalize()} Biedronka (gazetka)"
            store_product_id = get_or_create(
                self.sb, "store_products",
                {"store_id": self.store_id, "name": product_name},
                {"unit": unit, "unit_amount": unit_amount},
            )
            # Promocja w kolejnej gazetce bywa na innym opakowaniu niż
            # poprzednia (raz kostka 200 g, raz 300 g) — cena bez aktualnej
            # gramatury byłaby policzona wobec starego opakowania.
            self.sb.table("store_products").update(
                {"unit": unit, "unit_amount": unit_amount}
            ).eq("id", store_product_id).execute()

            replace_price(self.sb, store_product_id, "flyer-ocr",
                          c["package_price"], valid_from, valid_to)

            existing_mapping = self.sb.table("ingredient_mappings").select("id") \
                .eq("ingredient_id", ingredient_id) \
                .eq("store_product_id", store_product_id).limit(1).execute()
            if not existing_mapping.data:
                self.sb.table("ingredient_mappings").insert({
                    "ingredient_id": ingredient_id,
                    "store_product_id": store_product_id,
                    "conversion_factor": round(unit_amount / 100, 4),
                    "priority": 5,
                }).execute()

            saved += 1

        return saved


if __name__ == "__main__":
    result = BiedronkaScraper().scrape()
    print(f"\n[Biedronka] Podsumowanie: {result}")
