"""
leaflet_ocr.py — odczyt cen ze stron gazetki po UKŁADZIE GRAFICZNYM.

Poprzednie podejście spłaszczało stronę do jednego ciągu tekstu i szukało
nazwy składnika w oknie ~200 znaków przed ceną. Strona gazetki to jednak
siatka kafelków, a kolejność czytania OCR nie odpowiada układowi: cena
bywa oddzielona od swojej nazwy setkami znaków z sąsiedniego kafelka.
Efekt: z 52 stron wyciągaliśmy ceny dla 2 składników.

Tutaj korzystamy z tego, że tesseract w trybie TSV podaje ramkę każdego
słowa, więc cenę wiążemy z nazwą po ODLEGŁOŚCI NA STRONIE. Zmierzone na
prawdziwej gazetce (probe_flyer_layout.py): cena "4,59" leżała 116 px pod
napisem "Olej rzepakowy", w odległości 156 px — relacja jest wyraźna.

Ustawienia OCR też są zmierzone, nie zgadnięte (probe_ocr_settings.py,
strona produktowa gazetki):
    psm 3  (obecne), 1x -> 137 słów, 5 cen
    psm 11,          1x -> 169 słów, 8 cen
    psm 11,          2x -> 202 słowa, 9 cen   <- wybrane
Powiększenie 2x i tryb "rzadkiego tekstu" dają ~+50% słów i ~+80% cen.
"""
import os
import re
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingredient_catalog import (
    fuzzy_ingredient,
    is_plausible,
    unit_for,
    unit_price_of,
)

OCR_PSM = "11"          # sparse text — strona gazetki to plakat, nie akapit
OCR_UPSCALE = 2         # duże, stylizowane napisy czytają się lepiej powiększone
MIN_CONFIDENCE = 40

# Cena na gazetce bywa złożona z dwóch tokenów ("5" i "99" obok siebie,
# bo grosze są mniejszą czcionką), więc oprócz pełnej ceny zbieramy też
# same liczby i sklejamy je w PRICE_MAX_PART_GAP pikselach od siebie.
FULL_PRICE = re.compile(r'^(\d{1,3})[,.](\d{2})$')
INTEGER_PART = re.compile(r'^\d{1,3}$')
DECIMAL_PART = re.compile(r'^\d{2}$')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}


class Token:
    __slots__ = ("text", "left", "top", "width", "height", "conf")

    def __init__(self, text: str, left: int, top: int, width: int, height: int, conf: float):
        self.text = text
        self.left, self.top, self.width, self.height = left, top, width, height
        self.conf = conf

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2

    def distance_to(self, other: "Token") -> float:
        return ((self.cx - other.cx) ** 2 + (self.cy - other.cy) ** 2) ** 0.5

    def __repr__(self) -> str:
        return f"Token({self.text!r} @({self.left},{self.top}) h={self.height})"


def ocr_page(image_url: str, timeout: int = 120) -> tuple[list[Token], int]:
    """Słowa strony gazetki z ramkami. Zwraca (tokeny, szerokość strony)."""
    resp = requests.get(image_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    raw_path = "/tmp/leaflet_page_raw.png"
    with open(raw_path, "wb") as f:
        f.write(resp.content)

    image = Image.open(raw_path)
    scaled = image.resize((image.width * OCR_UPSCALE, image.height * OCR_UPSCALE), Image.LANCZOS)
    ocr_path = "/tmp/leaflet_page_ocr.png"
    scaled.save(ocr_path)

    out = subprocess.run(
        ["tesseract", ocr_path, "stdout", "-l", "pol", "--psm", OCR_PSM, "tsv"],
        capture_output=True, text=True, timeout=timeout,
    ).stdout

    tokens = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        if conf < MIN_CONFIDENCE:
            continue
        tokens.append(Token(text, int(parts[6]), int(parts[7]),
                            int(parts[8]), int(parts[9]), conf))

    return tokens, scaled.width


def find_prices(tokens: list[Token], page_width: int) -> list[tuple[Token, float]]:
    """Tokeny wyglądające na cenę, wraz z kwotą. Obsługuje też ceny
    rozbite na dwa tokeny ("5" obok "99"), bo grosze bywają mniejszą
    czcionką i tesseract rozdziela je na osobne słowa."""
    found: list[tuple[Token, float]] = []
    used: set[int] = set()

    for i, t in enumerate(tokens):
        m = FULL_PRICE.match(t.text)
        if m:
            found.append((t, float(f"{m.group(1)}.{m.group(2)}")))
            used.add(i)

    max_gap = page_width * 0.04
    for i, t in enumerate(tokens):
        if i in used or not INTEGER_PART.match(t.text):
            continue
        for j, other in enumerate(tokens):
            if j == i or j in used or not DECIMAL_PART.match(other.text):
                continue
            # Grosze stoją tuż obok złotówek i mniej więcej na tej samej
            # wysokości; wykluczamy przypadkowe pary z innych kafelków.
            if other.left < t.left or other.left - (t.left + t.width) > max_gap:
                continue
            if abs(other.top - t.top) > t.height:
                continue
            found.append((t, float(f"{t.text}.{other.text}")))
            used.add(i)
            used.add(j)
            break

    return found


# Cena z dopiskiem "/kg", "/l", "/100 g" to cena JEDNOSTKOWA podana obok
# ceny opakowania — nie wolno jej wziąć za kwotę do zapłaty.
UNIT_PRICE_SUFFIX = re.compile(r'^/?\s*(kg|l|szt|100)\b', re.IGNORECASE)
# Gramatura jako jeden token ("500g") albo dwa ("500" + "g").
SPEC_ONE_TOKEN = re.compile(r'^(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|szt)\.?$', re.IGNORECASE)
SPEC_NUMBER = re.compile(r'^\d+(?:[.,]\d+)?$')
SPEC_UNIT = re.compile(r'^(kg|g|ml|l|szt)\.?$', re.IGNORECASE)

MAX_NAME_DISTANCE_RATIO = 0.22   # ułamek szerokości strony
MAX_SPEC_DISTANCE_RATIO = 0.18


def _normalise_spec(amount: float, unit: str) -> tuple[str, float]:
    unit = unit.lower().rstrip(".")
    if unit == "kg":
        return ("g", amount * 1000)
    if unit == "l":
        return ("ml", amount * 1000)
    if unit == "szt":
        return ("szt", amount)
    return (unit, amount)


def _find_specs(tokens: list[Token], page_width: int) -> list[tuple[Token, str, float]]:
    """Tokeny z wielkością opakowania, znormalizowane do (jednostka, ilość)."""
    specs: list[tuple[Token, str, float]] = []
    max_gap = page_width * 0.03

    for i, t in enumerate(tokens):
        m = SPEC_ONE_TOKEN.match(t.text)
        if m:
            unit, amount = _normalise_spec(float(m.group(1).replace(",", ".")), m.group(2))
            specs.append((t, unit, amount))
            continue

        if not SPEC_NUMBER.match(t.text):
            continue
        for other in tokens:
            if other is t or not SPEC_UNIT.match(other.text):
                continue
            if other.left < t.left or other.left - (t.left + t.width) > max_gap:
                continue
            if abs(other.top - t.top) > t.height:
                continue
            unit, amount = _normalise_spec(float(t.text.replace(",", ".")), other.text)
            specs.append((t, unit, amount))
            break

    return specs


def _is_unit_price(price_token: Token, tokens: list[Token], page_width: int) -> bool:
    max_gap = page_width * 0.05
    for t in tokens:
        if t is price_token or not UNIT_PRICE_SUFFIX.match(t.text):
            continue
        if t.left < price_token.left:
            continue
        if t.left - (price_token.left + price_token.width) > max_gap:
            continue
        if abs(t.top - price_token.top) > price_token.height:
            continue
        return True
    return False


def extract_candidates(tokens: list[Token], page_width: int, debug: bool = False) -> list[dict]:
    """Ceny promocyjne wyciągnięte ze strony gazetki: każdą cenę wiążemy
    z NAJBLIŻSZĄ przestrzennie nazwą składnika i najbliższą gramaturą.

    Zwraca listę {ingredient_name, package_price, unit, unit_amount,
    unit_price} — tylko dopasowania, które przeszły kontrolę
    prawdopodobieństwa ceny."""
    names = [(t, ing) for t in tokens if (ing := fuzzy_ingredient(t.text))]
    if not names:
        return []

    specs = _find_specs(tokens, page_width)
    max_name_distance = page_width * MAX_NAME_DISTANCE_RATIO
    max_spec_distance = page_width * MAX_SPEC_DISTANCE_RATIO

    candidates: list[dict] = []
    for price_token, amount_pln in find_prices(tokens, page_width):
        if _is_unit_price(price_token, tokens, page_width):
            continue

        name_token, ingredient_name, name_distance = None, None, None
        for t, ing in names:
            d = price_token.distance_to(t)
            if name_distance is None or d < name_distance:
                name_token, ingredient_name, name_distance = t, ing, d
        if name_distance is None or name_distance > max_name_distance:
            continue

        base_unit = unit_for(ingredient_name)
        best_spec, spec_distance = None, None
        for t, unit, spec_amount in specs:
            if unit != base_unit:
                continue
            d = price_token.distance_to(t)
            if spec_distance is None or d < spec_distance:
                best_spec, spec_distance = (unit, spec_amount), d
        if best_spec is None or spec_distance > max_spec_distance:
            if debug:
                print(f"      [gazetka] {amount_pln} zł przy '{name_token.text}' "
                      f"({ingredient_name}) — brak gramatury w pobliżu, pomijam")
            continue

        unit, unit_amount = best_spec
        unit_price = unit_price_of(ingredient_name, amount_pln, unit, unit_amount)
        if unit_price is None:
            continue

        if not is_plausible(ingredient_name, unit_price):
            if debug:
                print(f"      [gazetka] odrzucam {ingredient_name}: {amount_pln} zł "
                      f"za {unit_amount:g}{unit} = {round(unit_price, 3)} zł/j. "
                      f"(poza zakresem wiarygodności)")
            continue

        if debug:
            print(f"      [gazetka] {ingredient_name}: {amount_pln} zł za {unit_amount:g}{unit} "
                  f"(nazwa '{name_token.text}' w {name_distance:.0f}px, "
                  f"gramatura w {spec_distance:.0f}px)")

        candidates.append({
            "ingredient_name": ingredient_name,
            "package_price": amount_pln,
            "unit": unit,
            "unit_amount": unit_amount,
            "unit_price": unit_price,
        })

    return candidates
