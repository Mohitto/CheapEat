"""
probe_flyer_page.py — co OCR naprawdę widzi na KONKRETNEJ stronie gazetki.

Scraper przy 96-stronicowej gazetce nie może wypisywać wszystkiego, więc
gdy pojedyncza promocja nie trafia do bazy (masło z pierwszej strony po
1,99), nie da się stwierdzić, czy zawiodło rozpoznanie tekstu, wiązanie
ceny z nazwą, gramatura czy kontrola wiarygodności. Ten skrypt bierze
jedną stronę i pokazuje każdy z tych etapów osobno.

    python probe_flyer_page.py [fragment-slugu] [numer-strony]
    python probe_flyer_page.py codziennie 0
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from biedronka.leaflet_ocr import (
    _find_specs, extract_candidates, find_prices, ocr_page, tile_text,
    unit_price_scale,
)
from biedronka.scraper import find_uuid, get_page_image_urls
from ingredient_catalog import fuzzy_ingredient


def main() -> None:
    slug_part = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    page_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    flyers = scrapable_flyers()
    print(f"Gazetki do przeczytania ({len(flyers)}):")
    for f in flyers:
        print(f"  {f['slug']}  {f['valid_from']}..{f['valid_to']}"
              + ("  (zapowiedziana)" if f["is_upcoming"] else ""))

    matching = [f for f in flyers if slug_part in f["slug"]]
    if not matching:
        print(f"\nŻadna gazetka nie pasuje do '{slug_part}'")
        return
    flyer = matching[0]
    print(f"\n=== {flyer['slug']}, strona {page_index} ===")

    urls = get_page_image_urls(find_uuid("https://www.biedronka.pl" + flyer["path"]))
    print(f"stron: {len(urls)}")
    if page_index >= len(urls):
        print("taka strona nie istnieje")
        return

    tokens, page_width = ocr_page(urls[page_index])
    print(f"szerokość po powiększeniu: {page_width} px, słów: {len(tokens)}\n")

    print("--- WSZYSTKIE SŁOWA ---")
    print(" | ".join(t.text for t in tokens))

    print("\n--- NAZWY SKŁADNIKÓW ---")
    for t in tokens:
        ing = fuzzy_ingredient(t.text)
        if ing:
            print(f"  '{t.text}' -> {ing}  @({t.left},{t.top}) h={t.height}")

    print("\n--- CENY ---")
    for token, value in find_prices(tokens, page_width):
        scale = unit_price_scale(token, tokens, page_width)
        print(f"  {value:>8.2f} zł  z '{token.text}' @({token.left},{token.top}) "
              f"h={token.height}" + (f"  [cena jednostkowa /{scale}]" if scale else ""))
        print(f"        kafelek: {tile_text(token, tokens, page_width)[:220]}")

    print("\n--- GRAMATURY ---")
    for token, unit, amount in _find_specs(tokens, page_width):
        print(f"  {amount:g}{unit}  z '{token.text}' @({token.left},{token.top})")

    print("\n--- KANDYDACI (z uzasadnieniem odrzuceń) ---")
    for c in extract_candidates(tokens, page_width, debug=True):
        print(f"  => {c['ingredient_name']}: {c['package_price']} zł za "
              f"{c['unit_amount']:g}{c['unit']} "
              f"({round(c['unit_price'], 3)} zł/j.), warunek={c['bundle_units']}, "
              f"na wagę={c['sold_loose']}, ważne={c['valid_from']}..{c['valid_to']}")


if __name__ == "__main__":
    main()
