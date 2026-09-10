"""
probe_ocr_variants.py — dlaczego z pierwszej strony gazetki nie da się
odczytać ani jednej ceny, i co z tym zrobić.

Sonda probe_flyer_page.py pokazała rzecz zaskakującą: na stronie tytułowej
gazetki "Codziennie niskie ceny" tesseract czyta drobny druk bez pudła —
"PRZY ZAKUPIE 5", "OFERTA OD 10.09 DO 12.09", "Świeży filet z piersi
kurczaka" — a WIELKICH cen (1,99 / 5,99 / 14,99) nie zwraca w ogóle.
Nie myli ich; one po prostu nie występują w wyniku.

Hipotezy do sprawdzenia pomiarem, nie na wyczucie:
  a) skala — przy powiększeniu 2x cyfry ceny mają ~120 px wysokości,
     a tesseract odrzuca zbyt duże kształty jako grafikę, nie tekst;
  b) kolor — część cen to biel na czerwonym/żółtym tle, a odcienie
     szarości spłaszczają ten kontrast;
  c) tryb segmentacji strony;
  d) ograniczenie alfabetu do cyfr, gdy szukamy tylko kwot.

Każdy wariant dostaje tę samą stronę i jest oceniany tą samą miarą:
ile słów, ile z nich wygląda na cenę i czy wśród nich jest cena masła.
"""
import os
import subprocess
import sys

import requests
from PIL import Image, ImageChops, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from biedronka.leaflet_ocr import (
    DECIMAL_PART, FULL_PRICE, GLUED_PRICE, HEADERS, INTEGER_PART, Token,
)
from biedronka.scraper import find_uuid, get_page_image_urls

WORK = "/tmp/ocr_variant"


def load_page(slug_part: str, page_index: int) -> Image.Image:
    flyer = next(f for f in scrapable_flyers() if slug_part in f["slug"])
    print(f"gazetka: {flyer['slug']} ({flyer['valid_from']}..{flyer['valid_to']})")
    urls = get_page_image_urls(find_uuid("https://www.biedronka.pl" + flyer["path"]))
    print(f"stron: {len(urls)}, biorę stronę {page_index}")
    resp = requests.get(urls[page_index], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    path = f"{WORK}_src.png"
    with open(path, "wb") as f:
        f.write(resp.content)
    image = Image.open(path)
    print(f"rozmiar oryginału: {image.width}x{image.height}\n")
    return image


def scaled(image: Image.Image, factor: float) -> Image.Image:
    if factor == 1:
        return image
    return image.resize((int(image.width * factor), int(image.height * factor)), Image.LANCZOS)


def white_on_colour(image: Image.Image) -> Image.Image:
    """Biały napis na kolorowym tle -> czarny napis na białym tle.

    Piksel jest biały tylko wtedy, gdy jest jasny we WSZYSTKICH kanałach,
    więc minimum kanałów odróżnia biel od czerwieni (R wysokie, G/B niskie)
    i od żółci (R/G wysokie, B niskie)."""
    r, g, b = image.convert("RGB").split()
    lowest = ImageChops.darker(ImageChops.darker(r, g), b)
    return lowest.point(lambda v: 0 if v >= 205 else 255).convert("L")


def dark_on_colour(image: Image.Image) -> Image.Image:
    """Czarny napis na kolorowym tle -> czarny napis na białym tle."""
    r, g, b = image.convert("RGB").split()
    highest = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return highest.point(lambda v: 0 if v <= 110 else 255).convert("L")


def ocr(image: Image.Image, psm: str, config: list[str] | None = None) -> list[Token]:
    path = f"{WORK}.png"
    image.save(path)
    out = subprocess.run(
        ["tesseract", path, "stdout", "-l", "pol", "--psm", psm, *(config or []), "tsv"],
        capture_output=True, text=True, timeout=180,
    ).stdout
    tokens = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        if conf < 40:
            continue
        tokens.append(Token(parts[11].strip(), int(parts[6]), int(parts[7]),
                            int(parts[8]), int(parts[9]), conf))
    return tokens


def price_like(tokens: list[Token]) -> list[str]:
    """Tokeny, które w ogóle mogłyby być kwotą — pełną, sklejoną albo
    samą złotówką stojącą obok groszy."""
    found = []
    for t in tokens:
        if FULL_PRICE.match(t.text) or GLUED_PRICE.match(t.text):
            found.append(t.text)
        elif INTEGER_PART.match(t.text) and any(
            DECIMAL_PART.match(o.text) and o is not t
            and 0 <= o.left - (t.left + t.width) <= t.width
            and abs(o.top - t.top) <= t.height
            for o in tokens
        ):
            found.append(f"{t.text}+gr")
    return found


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    page = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    source = load_page(slug, page)

    digits_only = ["-c", "tessedit_char_whitelist=0123456789,."]

    variants = [
        ("szarość 2x, psm 11 (obecne)", lambda im: scaled(im, 2), "11", None),
        ("szarość 1x, psm 11",          lambda im: im,             "11", None),
        ("szarość 0.6x, psm 11",        lambda im: scaled(im, 0.6), "11", None),
        ("szarość 2x, psm 6",           lambda im: scaled(im, 2),  "6",  None),
        ("szarość 2x, psm 12",          lambda im: scaled(im, 2),  "12", None),
        ("szarość 2x, psm 11, tylko cyfry", lambda im: scaled(im, 2), "11", digits_only),
        ("szarość 1x, psm 11, tylko cyfry", lambda im: im,          "11", digits_only),
        ("biel-na-kolorze 2x, psm 11",  lambda im: scaled(white_on_colour(im), 2), "11", None),
        ("czerń-na-kolorze 2x, psm 11", lambda im: scaled(dark_on_colour(im), 2), "11", None),
        ("czerń-na-kolorze 2x, psm 11, tylko cyfry",
         lambda im: scaled(dark_on_colour(im), 2), "11", digits_only),
        ("biel-na-kolorze 2x, psm 11, tylko cyfry",
         lambda im: scaled(white_on_colour(im), 2), "11", digits_only),
        ("autokontrast 2x, psm 11",     lambda im: scaled(ImageOps.autocontrast(im.convert("L")), 2), "11", None),
    ]

    for name, prepare, psm, config in variants:
        try:
            tokens = ocr(prepare(source), psm, config)
        except Exception as e:
            print(f"{name:44s} BŁĄD: {e}")
            continue
        prices = price_like(tokens)
        print(f"{name:44s} słów={len(tokens):4d}  cenopodobnych={len(prices):3d}  {prices[:24]}")


if __name__ == "__main__":
    main()
