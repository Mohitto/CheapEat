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
  3. biedronka/leaflet_ocr.py — OCR ze współrzędnymi każdego słowa. Cenę
     wiążemy z nazwą produktu i gramaturą po ODLEGŁOŚCI NA STRONIE, bo
     gazetka to siatka kafelków i kolejność czytania tekstu nie odpowiada
     układowi. Silniki są dwa i oba darmowe (projekt ma pozostać
     bezpłatny, więc świadomie bez płatnych API wizyjnych): tesseract
     przegląda wszystkie strony, EasyOCR czyta te, na których coś jest —
     powód tego podziału opisuje docstring leaflet_ocr.py.

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
from ingredient_catalog import (
    INGREDIENT_DEFAULTS,
    INGREDIENT_KEYWORDS,
    fuzzy_ingredient,
    unit_price_of,
)

from .flyers import scrapable_flyers
from .leaflet_ocr import extract_candidates, ocr_page, ocr_page_precise

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

# Ile stron wolno przeczytać dokładnym (wolnym) silnikiem w jednym
# przebiegu. Przegląd tesseractem kosztuje ~1 s na stronę, dokładny odczyt
# ~25 s — bez sufitu jeden przebieg po pięciu gazetkach potrafiłby chodzić
# godzinami. Sufit jest wysoki i podnoszony zmienną środowiskową; gdy
# zadziała, widać to w podsumowaniu, więc nie obcina po cichu.
MAX_PRECISE_PAGES = int(os.environ.get("BIEDRONKA_MAX_PRECISE_PAGES", "150"))

# Najniższa cena promocyjna, w jaką jeszcze wierzymy — jako UŁAMEK ceny
# regularnej tego samego składnika ze sklepu.
#
# Sztywne widełki "zł za 100 g na kategorię" nie dają się ustawić dobrze.
# Trzeba je było rozluźnić, żeby przepuścić prawdziwe masło po 0,995
# zł/100 g z pierwszej strony gazetki — i tym samym wpuściły mięso
# mielone po 0,50 zł/100 g oraz ser żółty po 0,68 zł/100 g, czyli
# odczyty równie fałszywe co poprzednie. Cena regularna jest lepszym
# punktem odniesienia, bo bierze się z tego samego sklepu i tej samej
# kategorii, i sama nadąża za rynkiem. Nawet "-66% TANIEJ" zostawia
# jedną trzecią ceny, więc oferta poniżej 30% jest niemal na pewno
# błędem odczytu, a nie okazją.
MIN_PROMO_FRACTION_OF_REGULAR = 0.30

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
    """Adresy WSZYSTKICH stron gazetki, bez powtórzeń.

    "images_desktop" to rozkładówki: każda pozycja ma listę `images` z
    dwiema stronami (okładka ma pustą lewą połowę). Wcześniejsza wersja
    brała z tej listy pierwszy niepusty adres i przerywała, więc z
    96-stronicowej gazetki czytaliśmy 49 stron — całą prawą kolumnę
    rozkładówek pomijaliśmy w milczeniu.

    "images_mobile" podaje te same pliki po jednym na stronę i jest
    naturalniejszym źródłem; desktopowe rozkładówki zostają jako zapas,
    bo to one były sprawdzone na żywo."""
    api_url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    urls: list[str] = []
    seen: set[str] = set()

    def add(img_url: str | None) -> None:
        if img_url and img_url not in seen:
            seen.add(img_url)
            urls.append(img_url)

    for page in data.get("images_mobile") or []:
        add(page.get("image"))
    for page in data.get("images_desktop") or []:
        for img_url in page.get("images", []):
            add(img_url)

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
            return {"flyers": 0, "pages_scanned": 0, "pages_read_precisely": 0,
                    "ingredients_found": 0, "saved": 0}

        print(f"[Biedronka] Gazetki do przeczytania: {len(flyers)}")
        for f in flyers:
            kiedy = "zapowiedziana" if f["is_upcoming"] else "obowiązuje"
            print(f"[Biedronka]   {f['slug']}: {f['valid_from']} .. {f['valid_to']} ({kiedy})")

        # Faza 1 — przegląd. Tesseract po każdej stronie każdej gazetki:
        # tanio i tylko po to, żeby wiedzieć, gdzie w ogóle stoi nazwa
        # któregoś z naszych składników.
        promising: list[dict] = []
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
                    scout_tokens, _ = ocr_page(image_url)
                except Exception as e:
                    print(f"[Biedronka] {flyer['slug']} strona {i}: błąd OCR ({e}), pomijam")
                    continue

                pages_scanned += 1
                names = {ing for t in scout_tokens if (ing := fuzzy_ingredient(t.text))}
                if names:
                    promising.append({"flyer": flyer, "index": i,
                                      "url": image_url, "names": names})

        # Kolejność ma znaczenie, bo faza 2 ma budżet: strona z trzema
        # naszymi składnikami jest warta więcej niż strona z jednym, a
        # gdyby zabrakło czasu, chcemy stracić te najmniej obiecujące.
        promising.sort(key=lambda page: len(page["names"]), reverse=True)
        print(f"[Biedronka] Stron ze składnikami: {len(promising)} z {pages_scanned}; "
              f"czytam dokładnie do {MAX_PRECISE_PAGES}")

        found_per_ingredient: dict[tuple, dict] = {}
        pages_read = 0

        # Faza 2 — odczyt. Tylko obiecujące strony i tylko silnikiem, który
        # widzi ceny (patrz leaflet_ocr.py: tesseract ich nie czyta).
        for page in promising[:MAX_PRECISE_PAGES]:
            flyer, i = page["flyer"], page["index"]
            try:
                tokens, page_width = ocr_page_precise(page["url"])
            except Exception as e:
                print(f"[Biedronka] {flyer['slug']} strona {i}: "
                      f"dokładny OCR nie zadziałał ({e}), pomijam")
                continue
            pages_read += 1

            candidates = extract_candidates(tokens, page_width, debug=DEBUG)

            # Strona ma nazwę naszego składnika, a mimo to nic z niej nie
            # wyszło — to jedyny przypadek, w którym warto zobaczyć surowy
            # odczyt. Bez tego nie da się odróżnić "OCR nie przeczytał"
            # od "przeczytał, ale nie umieliśmy powiązać ceny z nazwą".
            if DEBUG and not candidates:
                readable = [t for t in tokens if len(t.text) > 2 or t.text.isdigit()]
                print(f"[Biedronka] {flyer['slug']} s.{i}: {sorted(page['names'])} "
                      f"na stronie, ale bez ceny; OCR odczytał {len(tokens)} słów: "
                      f"{' | '.join(t.text for t in readable[:120])}")

            for c in candidates:
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
            "pages_read_precisely": pages_read,
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

            # Ostatnia kontrola, i najmocniejsza: cena promocyjna
            # porównana z ceną regularną tego samego składnika w tym samym
            # sklepie. Zakresy per kategoria są zgadywane raz i starzeją
            # się razem z rynkiem; ta liczba bierze się z danych.
            regular = cheapest_regular_unit_price(self.sb, ingredient_id, ingredient_name)
            if regular is not None and c["unit_price"] < regular * MIN_PROMO_FRACTION_OF_REGULAR:
                print(f"[Biedronka] ODRZUCAM {ingredient_name}: {c['package_price']} zł za "
                      f"{unit_amount:g}{unit} = {round(c['unit_price'], 3)} zł/j., "
                      f"czyli {c['unit_price'] / regular:.0%} ceny regularnej "
                      f"({round(regular, 3)} zł/j.) — to nie promocja, to zły odczyt")
                continue

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


def cheapest_regular_unit_price(sb, ingredient_id: str, ingredient_name: str) -> float | None:
    """Najniższa REGULARNA cena jednostkowa tego składnika w sklepie,
    albo None, gdy jeszcze żadnej nie znamy."""
    mappings = sb.table("ingredient_mappings").select("store_product_id") \
        .eq("ingredient_id", ingredient_id).execute().data

    best = None
    for mapping in mappings:
        product = sb.table("store_products").select("unit,unit_amount") \
            .eq("id", mapping["store_product_id"]).limit(1).execute().data
        if not product:
            continue
        unit, unit_amount = product[0].get("unit"), product[0].get("unit_amount")
        if not unit or not unit_amount or unit_amount <= 0:
            continue

        prices = sb.table("prices").select("gross_price") \
            .eq("store_product_id", mapping["store_product_id"]) \
            .eq("source", "shop-regular").execute().data
        for row in prices:
            unit_price = unit_price_of(ingredient_name, row["gross_price"], unit, unit_amount)
            if unit_price is not None and (best is None or unit_price < best):
                best = unit_price

    return best


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
