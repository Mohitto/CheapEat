"""
Scraper gazetki Biedronka — ceny promocyjne odczytywane z obrazków.

Biedronka NIE udostępnia cen gazetkowych jako danych (sprawdzone przez
scrapers/probe_biedronka_*.py — leaflet-api zwraca wyłącznie bitmapy
stron). Jedyna droga to OCR, i to on jest rdzeniem cen promocyjnych w tej
aplikacji:

  1. biedronka/flyers.py — WSZYSTKIE gazetki z /pl/gazetki wraz z okresem
     obowiązywania (data startu jest w slugu adresu). Czytamy też wydania
     zapowiedziane ("OD CZWARTKU"), ale zapisujemy je z ich prawdziwą datą
     startu — apka pokaże taką cenę dopiero, gdy zacznie obowiązywać, a
     wygasłe znikają same.
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
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import get_or_create, get_supabase, replace_price
from ingredient_catalog import INGREDIENT_DEFAULTS, INGREDIENT_KEYWORDS

from .flyers import scrapable_flyers
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
        """Czyta gazetki obowiązujące dzisiaj ORAZ już zapowiedziane.

        Wcześniej otwieraliśmy wyłącznie gazetki obowiązujące dzisiaj.
        Brzmi ostrożnie, a w praktyce oznaczało, że 9 września główna,
        96-stronicowa gazetka "oferta od 10.09" — z masłem po 1,99 na
        pierwszej stronie — nie była czytana w ogóle. Teraz czytamy ją od
        razu, ale każda cena dostaje prawdziwą datę startu, więc apka
        pokaże ją dopiero od 10.09 (patrz priceService.getCurrentPriceInfo)."""
        flyers = scrapable_flyers()
        if not flyers:
            print("[Biedronka] Brak gazetek do przeczytania")
            return {"flyers": 0, "pages_scanned": 0, "ingredients_found": 0, "saved": 0}

        print(f"[Biedronka] Gazetki do przeczytania: {len(flyers)}")
        for f in flyers:
            kiedy = "zapowiedziana" if f["is_upcoming"] else "obowiązuje"
            print(f"[Biedronka]   {f['slug']}: {f['valid_from']} .. {f['valid_to']} ({kiedy})")

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

                # Gazetki tematyczne są krótkie, a to w nich siedzą promocje
                # na nasze składniki (nabiał, mięso). Gdy z takiej strony nic
                # nie wyciągniemy, chcemy zobaczyć, co OCR w ogóle odczytał —
                # bez tego nie da się stwierdzić, czy zawiodło rozpoznanie
                # tekstu, czy dopasowanie ceny do nazwy.
                if DEBUG and len(image_urls) <= 4:
                    interesting = [t for t in tokens if len(t.text) > 2 or t.text.isdigit()]
                    print(f"[Biedronka] {flyer['slug']} s.{i}: OCR odczytał "
                          f"{len(tokens)} słów; treść: "
                          f"{' | '.join(t.text for t in interesting[:120])}")

                for c in extract_candidates(tokens, page_width, debug=DEBUG):
                    # Klucz obejmuje WARIANT oferty, nie samą kategorię.
                    # Promocja warunkowa ("5 kostek masła po 1,99") ma
                    # niższą cenę jednostkową niż pojedyncza kostka, więc
                    # przy kluczowaniu samą nazwą wypychała ją z bazy — a
                    # do przepisu na 30 g masła nikt nie kupi pięciu
                    # kostek. Oba warianty trafiają do bazy obok siebie i
                    # to apka wybiera tańszy dla konkretnej ilości.
                    key = (c["ingredient_name"], c["bundle_units"], c["sold_loose"])
                    previous = found_per_ingredient.get(key)
                    if previous is None or c["unit_price"] < previous["unit_price"]:
                        found_per_ingredient[key] = {**c, "flyer": flyer}
                        print(f"[Biedronka] {flyer['slug']} s.{i}: {c['ingredient_name']} -> "
                              f"{c['package_price']} zł za {c['unit_amount']:g}{c['unit']} "
                              f"({round(c['unit_price'], 4)} zł/j.)"
                              + (f" [przy zakupie {c['bundle_units']} szt.]"
                                 if c["bundle_units"] > 1 else "")
                              + (" [na wagę]" if c["sold_loose"] else ""))

        if DEBUG:
            priced = {key[0] for key in found_per_ingredient}
            missing = [n for n in INGREDIENT_KEYWORDS if n not in priced]
            print(f"[Biedronka] Kategorie bez ceny w gazetkach: {missing}")

        saved = self._save(found_per_ingredient)
        return {
            "flyers": len(flyers),
            "pages_scanned": pages_scanned,
            "ingredients_found": len(found_per_ingredient),
            "saved": saved,
        }

    def _save(self, found_per_ingredient: dict[tuple, dict]) -> int:
        if not found_per_ingredient:
            return 0

        saved = 0

        for (ingredient_name, bundle_units, sold_loose), c in found_per_ingredient.items():
            unit, unit_amount = c["unit"], c["unit_amount"]
            flyer = c["flyer"]
            valid_from, valid_to = _validity(c, flyer)

            ingredient_id = get_or_create(
                self.sb, "ingredients", {"name": ingredient_name},
                INGREDIENT_DEFAULTS.get(ingredient_name, {}),
            )

            product_name = _product_name(ingredient_name, c)
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


def _product_name(ingredient_name: str, c: dict) -> str:
    """Nazwa produktu sklepowego opisująca WARIANT oferty.

    Nazwa musi rozróżniać warianty, bo to po niej scraper odnajduje
    (get_or_create) swój wiersz — gdyby kostka masła i pakiet pięciu
    kostek nazywały się tak samo, każdy przebieg nadpisywałby jeden
    wariant drugim. Przy okazji użytkownik widzi wprost, na czym polega
    oferta, zamiast niewytłumaczalnie niskiej ceny."""
    label = [f"{ingredient_name.capitalize()} Biedronka (gazetka"]
    if c["bundle_units"] > 1:
        single = c["unit_amount"] / c["bundle_units"]
        label.append(f", {c['bundle_units']}x{single:g}{c['unit']} po {c['single_price']:.2f} zł")
    if c["sold_loose"]:
        label.append(", na wagę")
    if c["loyalty"]:
        label.append(", z kartą")
    return "".join(label) + ")"


def _validity(c: dict, flyer: dict) -> tuple[str, str]:
    """Okres obowiązywania ceny: z KAFELKA, gdy gazetka go wydrukowała
    ("OFERTA OD 10.09 DO 12.09"), inaczej z całej gazetki.

    Gazetka trwa tydzień, ale pojedyncza promocja bywa trzydniowa —
    bez daty z kafelka cena wisiałaby w apce jeszcze po jej wygaśnięciu,
    zamiast wrócić do ceny sprzed promocji."""
    tile_from = _tile_date(c.get("valid_from"), flyer["valid_from"])
    tile_to = _tile_date(c.get("valid_to"), flyer["valid_from"])
    if tile_from and tile_to and tile_from <= tile_to:
        # Data z kafelka odczytana przez OCR bywa przekręcona; ufamy jej
        # tylko wtedy, gdy trzyma się okolic gazetki, w której stoi.
        if abs((tile_from - flyer["valid_from"]).days) <= 14:
            return tile_from.isoformat(), tile_to.isoformat()
    return flyer["valid_from"].isoformat(), flyer["valid_to"].isoformat()


def _tile_date(day_month: tuple[int, int] | None, reference: date) -> date | None:
    """(dzień, miesiąc) z kafelka -> data. Rok bierzemy z gazetki, w
    której kafelek stoi; przy przełomie roku (gazetka grudniowa z ofertą
    "od 02.01") przesuwamy o rok do przodu."""
    if not day_month:
        return None
    day, month = day_month
    for year in (reference.year, reference.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= reference - timedelta(days=14):
            return candidate
    return None


if __name__ == "__main__":
    result = BiedronkaScraper().scrape()
    print(f"\n[Biedronka] Podsumowanie: {result}")
