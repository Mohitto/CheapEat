"""
test_leaflet_ocr.py — odczyt kafelka gazetki, na sztucznych tokenach OCR.

Gazetka jest obrazkiem, więc jedyny sposób sprawdzenia tej logiki bez
sieci i bez tesseracta to podać jej takie tokeny, jakie OCR zwraca z
prawdziwej strony. Kafelki poniżej są przepisane z pierwszej strony
gazetki "Codziennie niskie ceny" (nr 37/2026, oferta od 10.09): masło
"przy zakupie 5" po 1,99 i świeży filet z piersi kurczaka 14,99/kg na
wagę — dokładnie te dwa przypadki, na których poprzednia wersja
scrapera się wykładała.

Uruchomienie: python3 scrapers/test_leaflet_ocr.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.leaflet_ocr import Token, extract_candidates

PAGE_WIDTH = 2000


def tile(words: list[tuple[str, int, int, int, int]]) -> list[Token]:
    return [Token(text, left, top, width, height, 90.0)
            for text, left, top, width, height in words]


# Kafelek masła: znaczek "Z KARTĄ LUB APKĄ", warunek "PRZY ZAKUPIE 5",
# wielka cena złożona z "1" i uniesionego "99", czarny pasek z datami i
# opis produktu z gramaturą.
BUTTER_TILE = tile([
    ("Z", 1150, 760, 20, 26), ("KARTĄ", 1180, 760, 70, 26),
    ("LUB", 1260, 760, 45, 26), ("APKĄ", 1315, 760, 55, 26),
    ("PRZY", 1150, 800, 60, 28), ("ZAKUPIE", 1220, 800, 100, 28), ("5", 1330, 800, 18, 28),
    ("66%", 1150, 840, 55, 30), ("TANIEJ", 1215, 840, 90, 30),
    ("KAŻDA", 1150, 880, 75, 24), ("Z", 1235, 880, 18, 24),
    ("5", 1260, 880, 16, 24), ("SZTUK", 1285, 880, 70, 24),
    ("1", 1160, 920, 60, 90), ("99", 1228, 925, 46, 46),
    ("OFERTA", 1330, 1005, 80, 22), ("OD", 1420, 1005, 30, 22),
    ("10.09", 1458, 1005, 60, 22), ("DO", 1526, 1005, 30, 22),
    ("12.09", 1564, 1005, 60, 22),
    ("Masło", 1150, 1070, 70, 26), ("Ekstra", 1228, 1070, 70, 26),
    ("z", 1306, 1070, 14, 26), ("Polskiej", 1328, 1070, 85, 26),
    ("Mleczarni,", 1420, 1070, 110, 26),
    ("200", 1538, 1070, 45, 26), ("g", 1590, 1070, 14, 26),
])

# Ten sam produkt bez warunku "przy zakupie" — zwykła kostka.
PLAIN_BUTTER_TILE = tile([
    ("5", 1160, 920, 60, 90), ("99", 1228, 925, 46, 46),
    ("Masło", 1150, 1070, 70, 26), ("Ekstra", 1228, 1070, 70, 26),
    ("200", 1330, 1070, 45, 26), ("g", 1382, 1070, 14, 26),
])

# Produkt na wagę: jedyna cena na kafelku to cena za kilogram, bez
# żadnej gramatury opakowania — bo opakowania nie ma.
LOOSE_CHICKEN_TILE = tile([
    ("39%", 300, 820, 55, 30), ("TANIEJ", 365, 820, 90, 30),
    ("14", 300, 870, 90, 100), ("99", 400, 875, 50, 50),
    ("/kg", 455, 920, 40, 30),
    ("Świeży", 300, 1010, 80, 26), ("filet", 388, 1010, 50, 26),
    ("z", 446, 1010, 14, 26), ("piersi", 468, 1010, 60, 26),
    ("kurczaka", 536, 1010, 100, 26),
])


def check(name: str, condition: bool, detail: str = "") -> bool:
    print(("  OK   " if condition else "  BŁĄD ") + name + (f" — {detail}" if detail else ""))
    return condition


def main() -> int:
    ok = True

    print("Kafelek: masło ekstra 200 g, 1,99 przy zakupie 5")
    got = extract_candidates(BUTTER_TILE, PAGE_WIDTH)
    ok &= check("znaleziono dokładnie jedną ofertę", len(got) == 1, f"{len(got)}")
    if got:
        c = got[0]
        ok &= check("kategoria to masło", c["ingredient_name"] == "masło", c["ingredient_name"])
        ok &= check("płacisz za pięć kostek", c["package_price"] == 9.95, str(c["package_price"]))
        ok &= check("dostajesz 5 x 200 g", c["unit_amount"] == 1000, str(c["unit_amount"]))
        ok &= check("warunek zapisany", c["bundle_units"] == 5, str(c["bundle_units"]))
        ok &= check("cena jednej sztuki zachowana", c["single_price"] == 1.99, str(c["single_price"]))
        ok &= check("wymaga karty", c["loyalty"] is True)
        ok &= check("okres z kafelka", c["valid_from"] == (10, 9) and c["valid_to"] == (12, 9),
                    f"{c['valid_from']}..{c['valid_to']}")
        ok &= check("nie jest na wagę", c["sold_loose"] is False)

    print("\nKafelek: masło ekstra 200 g za 5,99 (bez warunku)")
    got = extract_candidates(PLAIN_BUTTER_TILE, PAGE_WIDTH)
    ok &= check("znaleziono ofertę", len(got) == 1, f"{len(got)}")
    if got:
        c = got[0]
        ok &= check("cena to cena kostki", c["package_price"] == 5.99, str(c["package_price"]))
        ok &= check("opakowanie to 200 g", c["unit_amount"] == 200, str(c["unit_amount"]))
        ok &= check("bez warunku zakupu", c["bundle_units"] == 1, str(c["bundle_units"]))

    print("\nKafelek: filet z piersi kurczaka 14,99/kg na wagę")
    got = extract_candidates(LOOSE_CHICKEN_TILE, PAGE_WIDTH)
    ok &= check("znaleziono ofertę", len(got) == 1, f"{len(got)}")
    if got:
        c = got[0]
        ok &= check("kategoria to kurczak pierś", c["ingredient_name"] == "kurczak pierś",
                    c["ingredient_name"])
        ok &= check("rozpoznany jako na wagę", c["sold_loose"] is True)
        ok &= check("liczone za gram", round(c["package_price"], 5) == 0.01499,
                    str(c["package_price"]))
        ok &= check("cena za 100 g zgadza się z gazetką",
                    round(c["unit_price"], 3) == 1.499, str(round(c["unit_price"], 4)))

    print("\nWYNIK:", "wszystko zgodne z gazetką" if ok else "są rozbieżności")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
