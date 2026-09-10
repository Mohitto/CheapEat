"""
probe_page_tiles.py — czy pocięcie strony na kafelki odblokowuje ceny.

Stan wiedzy: na stronie tytułowej tesseract czyta drobny druk bezbłędnie,
a wielkich cen (1,99 / 5,99 / 14,99) nie zwraca w żadnym z dwunastu
sprawdzonych wariantów przygotowania obrazu, przy żadnej skali i żadnym
trybie segmentacji. Większego renderu API nie oferuje — 1146x1800 to
jedyny rozmiar.

Zostaje hipoteza o SEGMENTACJI CAŁEJ STRONY: tesseract analizuje układ
zanim zacznie czytać, i na plakacie z ogromnymi cyframi na kolorowych
plamach klasyfikuje te cyfry jako grafikę, nie tekst. Jeśli tak jest, to
ten sam obrazek pocięty na kawałki — gdzie cena przestaje być anomalią
wielkości, a staje się największym tekstem kawałka — powinien się
odczytać.

Test: ta sama strona, siatka nachodzących na siebie kafelków, ten sam
sposób liczenia "co wygląda na cenę", plus współrzędne w układzie całej
strony, żeby dało się to potem złożyć z powrotem.
"""
import os
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from biedronka.leaflet_ocr import (
    DECIMAL_PART, FULL_PRICE, GLUED_PRICE, HEADERS, INTEGER_PART, Token,
)
from biedronka.scraper import find_uuid, get_page_image_urls

COLUMNS, ROWS = 3, 4
OVERLAP = 0.15
UPSCALE = 3


def ocr_tokens(image: Image.Image, psm: str) -> list[Token]:
    path = "/tmp/tile.png"
    image.save(path)
    out = subprocess.run(
        ["tesseract", path, "stdout", "-l", "pol", "--psm", psm, "tsv"],
        capture_output=True, text=True, timeout=120,
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
    out = []
    for t in tokens:
        if FULL_PRICE.match(t.text) or GLUED_PRICE.match(t.text):
            out.append(t.text)
        elif INTEGER_PART.match(t.text) and any(
            DECIMAL_PART.match(o.text) and o is not t
            and 0 <= o.left - (t.left + t.width) <= t.width
            and abs(o.top - t.top) <= t.height
            for o in tokens
        ):
            out.append(f"{t.text}+gr")
    return out


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    page_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    flyer = next(f for f in scrapable_flyers() if slug in f["slug"])
    urls = get_page_image_urls(find_uuid("https://www.biedronka.pl" + flyer["path"]))
    print(f"{flyer['slug']}: stron po poprawce {len(urls)}, biorę {page_index}")

    resp = requests.get(urls[page_index], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    with open("/tmp/page.png", "wb") as f:
        f.write(resp.content)
    page = Image.open("/tmp/page.png").convert("RGB")
    print(f"strona: {page.width}x{page.height}\n")

    for psm in ("11", "6"):
        whole = page.resize((page.width * 2, page.height * 2), Image.LANCZOS)
        base = price_like(ocr_tokens(whole, psm))
        print(f"CAŁA STRONA, psm {psm}, 2x: {len(base)} cenopodobnych {base[:16]}")

    tile_w = page.width / COLUMNS
    tile_h = page.height / ROWS
    pad_x, pad_y = tile_w * OVERLAP, tile_h * OVERLAP

    print(f"\nKAFELKI {COLUMNS}x{ROWS} (nachodzące o {int(OVERLAP * 100)}%), "
          f"powiększenie {UPSCALE}x, psm 11:")
    total = []
    for row in range(ROWS):
        for col in range(COLUMNS):
            box = (
                max(0, int(col * tile_w - pad_x)),
                max(0, int(row * tile_h - pad_y)),
                min(page.width, int((col + 1) * tile_w + pad_x)),
                min(page.height, int((row + 1) * tile_h + pad_y)),
            )
            crop = page.crop(box)
            scaled = crop.resize((crop.width * UPSCALE, crop.height * UPSCALE), Image.LANCZOS)
            tokens = ocr_tokens(scaled, "11")
            prices = price_like(tokens)
            total.extend(prices)
            print(f"  [{row},{col}] {box}  słów={len(tokens):3d}  ceny={prices}")

    print(f"\nRAZEM z kafelków: {len(total)} cenopodobnych")


if __name__ == "__main__":
    main()
