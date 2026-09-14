"""
test_flyer_ocr.py — odczyt kafelka gazetki, na sztucznych tokenach OCR.

Test wspólnego silnika (flyer_ocr.py), nie samej Biedronki — ale
przypadki testowe są z prawdziwej gazetki Biedronki, bo to na razie
jedyny sklep z gazetką jako obrazkiem. Kolejny sklep tego typu powinien
dołożyć tu swoje własne kafelki (inny krój cen, inna forma promocji
warunkowych), a nie zakładać, że te same wystarczą.

Gazetka jest obrazkiem, więc jedyny sposób sprawdzenia tej logiki bez
sieci i bez tesseracta to podać jej takie tokeny, jakie OCR zwraca z
prawdziwej strony. Kafelki poniżej są przepisane z pierwszej strony
gazetki "Codziennie niskie ceny" (nr 37/2026, oferta od 10.09): masło
"przy zakupie 5" po 1,99 i świeży filet z piersi kurczaka 14,99/kg na
wagę — dokładnie te dwa przypadki, na których poprzednia wersja
scrapera się wykładała.

Uruchomienie: python3 scrapers/test_flyer_ocr.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flyer_ocr import Token, _split_fragment, extract_candidates

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


# --- to samo, ale tak jak czyta to EasyOCR ---------------------------------
#
# EasyOCR zwraca całe frazy, nie pojedyncze słowa, i ma własny zestaw
# pomyłek. Poniższe fragmenty są PRZEPISANE Z JEGO PRAWDZIWEGO WYJŚCIA dla
# strony tytułowej (probe_ocr_engines.py, gazetka nr 37/2026) — razem z
# błędami, które trzeba wytrzymać:
#   "200 g"    -> "2009"   (litera g nie do odróżnienia od dziewiątki)
#   "66%"      -> "669"    (znak procenta jako dziewiątka)
#   "OD 10.09" -> "OD 10,09" (przecinek zamiast kropki w dacie)
#   "Z 5 SZTUK"-> "Z5 SZTUK"
EASYOCR_BUTTER_FRAGMENTS = [
    ("ZKARTĄ LUB APKĄ", 1290, 770, 200, 40),
    ("PRZY ZAKUPIE 5", 1285, 820, 210, 46),
    ("669 TANIEJ", 1285, 875, 200, 60),
    ("KAŻDA Z5 SZTUK", 1290, 940, 190, 34),
    ("199", 1330, 980, 150, 120),
    ("OFERTA", 1560, 1120, 110, 26),
    ("OD 10,09 DO 12.09", 1690, 1120, 230, 26),
    ("Masło Ekstra z Polskiej Mleczarni; 2009", 1280, 1160, 560, 36),
    ("Limit dzienny 5 szt. na kartę Moja Biedronka:", 1280, 1205, 520, 28),
    ("MASŁO", 1800, 460, 180, 60),
    ("ekstra", 1820, 530, 120, 34),
]

EASYOCR_BUTTER_TILE = [
    token
    for text, left, top, width, height in EASYOCR_BUTTER_FRAGMENTS
    for token in _split_fragment(text, left, top, width, height, 85.0)
]

EASYOCR_PAGE_WIDTH = 2292


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

    print("\nKafelek masła tak, jak czyta go EasyOCR (z jego pomyłkami)")
    got = extract_candidates(EASYOCR_BUTTER_TILE, EASYOCR_PAGE_WIDTH)
    ok &= check("znaleziono dokładnie jedną ofertę", len(got) == 1,
                f"{len(got)}: {[(c['ingredient_name'], c['package_price']) for c in got]}")
    if got:
        c = got[0]
        ok &= check("kategoria to masło", c["ingredient_name"] == "masło", c["ingredient_name"])
        ok &= check("cena sklejona '199' odczytana jako 1,99",
                    c["single_price"] == 1.99, str(c["single_price"]))
        ok &= check("gramatura '2009' odczytana jako 200 g",
                    c["unit_amount"] == 1000, str(c["unit_amount"]))
        ok &= check("płacisz za pięć kostek", c["package_price"] == 9.95, str(c["package_price"]))
        ok &= check("rabat '669 TANIEJ' nie stał się ceną 6,69",
                    c["package_price"] != 6.69)
        ok &= check("data z przecinkiem odczytana", c["valid_from"] == (10, 9),
                    str(c["valid_from"]))
        ok &= check("wymaga karty", c["loyalty"] is True)

    # --- masło, gazetka nr 38/2026 (tydzień od 14.09) --------------------
    #
    # Ten sam produkt, tydzień później: dwie osobne oferty na jednej
    # stronie, z DWOMA RÓŻNYMI zapisami daty, żadnym z nich "OD dd.mm DO
    # dd.mm" — dokładnie ten format, pod który był pisany OFFER_PERIOD
    # (teraz OFFER_PERIOD_OD_DO). Bez tych dwóch dodatkowych wzorców obie
    # oferty dostawałyby ważność całej gazetki zamiast swojej prawdziwej,
    # krótszej. Przepisane ze zrzutu ekranu prawdziwej gazetki w apce.
    print("\nKafelek masła: 'TYLKO W PONIEDZIAŁEK 14.09' (jeden dzień)")
    monday_tile = tile([
        ("TYLKO", 150, 380, 60, 30), ("W", 215, 380, 20, 30),
        ("PONIEDZIAŁEK", 240, 380, 190, 30), ("14.09", 435, 380, 80, 30),
        ("ZKARTĄ", 150, 460, 90, 40), ("LUB", 245, 460, 40, 40), ("APKĄ", 290, 460, 55, 40),
        ("PRZY", 150, 510, 60, 46), ("ZAKUPIE", 215, 510, 105, 46), ("5", 325, 510, 15, 46),
        ("66%", 150, 565, 55, 60), ("TANIEJ", 210, 565, 120, 60),
        ("KAŻDA", 150, 640, 70, 34), ("Z", 225, 640, 18, 34), ("5", 248, 640, 15, 34), ("SZTUK", 268, 640, 70, 34),
        ("199", 160, 680, 150, 120),
        ("Cena", 420, 505, 40, 24), ("przed", 465, 505, 45, 24), ("obniżką:", 515, 505, 75, 24),
        ("5,99", 610, 500, 70, 30),
        ("Cena", 420, 555, 40, 22), ("za", 465, 555, 25, 22), ("1", 495, 555, 12, 22), ("szt.", 512, 555, 32, 22),
        ("bez", 550, 555, 32, 22), ("karty", 587, 555, 45, 22), ("MB", 637, 555, 27, 22),
        ("poza", 670, 555, 38, 22), ("limitem:", 713, 555, 68, 22),
        ("5,99", 420, 595, 60, 24), ("29,95", 490, 595, 60, 24), ("zł/kg", 555, 595, 50, 24),
        ("Masło", 150, 1150, 71, 32), ("Ekstra", 226, 1150, 86, 32), ("z", 316, 1150, 14, 32),
        ("Polskiej", 335, 1150, 114, 32), ("Mleczarni,", 454, 1150, 143, 32), ("200", 602, 1150, 45, 32), ("g", 652, 1150, 14, 32),
        ("Limit", 150, 1200, 50, 26), ("dzienny", 205, 1200, 68, 26), ("5", 278, 1200, 15, 26),
        ("szt.", 298, 1200, 32, 26), ("na", 335, 1200, 22, 26), ("kartę", 362, 1200, 50, 26),
        ("Moja", 417, 1200, 42, 26), ("Biedronka.", 464, 1200, 96, 26),
    ])
    got = extract_candidates(monday_tile, 2292)
    masło = [c for c in got if c["ingredient_name"] == "masło"]
    ok &= check("dokładnie jedna oferta na masło (nie łapie 'ceny przed obniżką')",
                len(masło) == 1, f"{len(masło)}: {[(c['package_price'], c.get('bundle_units')) for c in masło]}")
    if masło:
        c = masło[0]
        ok &= check("przy zakupie 5 sztuk po 1,99", c["bundle_units"] == 5 and c["single_price"] == 1.99,
                    f"bundle={c['bundle_units']} single={c['single_price']}")
        ok &= check("jeden dzień: początek = koniec = 14.09",
                    c["valid_from"] == (14, 9) and c["valid_to"] == (14, 9),
                    f"{c['valid_from']}..{c['valid_to']}")

    print("\nKafelek masła: 'WTOREK – SOBOTA 15.09-19.09' (zakres dat myślnikiem)")
    tue_sat_tile = tile([
        ("WTOREK", 1250, 380, 90, 30), ("–", 1345, 380, 15, 30), ("SOBOTA", 1365, 380, 90, 30),
        ("15.09-19.09", 1460, 380, 160, 30),
        ("ZKARTĄ", 1250, 460, 90, 40), ("LUB", 1345, 460, 40, 40), ("APKĄ", 1390, 460, 55, 40),
        ("PRZY", 1250, 510, 60, 46), ("ZAKUPIE", 1315, 510, 105, 46), ("3", 1425, 510, 15, 46),
        ("58%", 1250, 565, 55, 60), ("TANIEJ", 1310, 565, 120, 60),
        ("KAŻDA", 1250, 640, 70, 34), ("Z", 1325, 640, 18, 34), ("3", 1348, 640, 15, 34), ("SZTUK", 1368, 640, 70, 34),
        ("249", 1260, 680, 150, 120),
        ("Cena", 1520, 505, 40, 24), ("przed", 1565, 505, 45, 24), ("obniżką:", 1615, 505, 75, 24),
        ("5,99", 1710, 500, 70, 30),
        ("Masło", 1250, 1150, 71, 32), ("Ekstra", 1326, 1150, 86, 32), ("z", 1416, 1150, 14, 32),
        ("Polskiej", 1435, 1150, 114, 32), ("Mleczarni,", 1554, 1150, 143, 32), ("200", 1702, 1150, 45, 32), ("g", 1752, 1150, 14, 32),
        ("Limit", 1250, 1200, 50, 26), ("dzienny", 1305, 1200, 68, 26), ("6", 1378, 1200, 15, 26),
        ("szt.", 1398, 1200, 32, 26), ("na", 1435, 1200, 22, 26), ("kartę", 1462, 1200, 50, 26),
        ("Moja", 1517, 1200, 42, 26), ("Biedronka.", 1564, 1200, 96, 26),
    ])
    got = extract_candidates(tue_sat_tile, 2292)
    masło = [c for c in got if c["ingredient_name"] == "masło"]
    ok &= check("dokładnie jedna oferta na masło", len(masło) == 1,
                f"{len(masło)}: {[(c['package_price'], c.get('bundle_units')) for c in masło]}")
    if masło:
        c = masło[0]
        ok &= check("przy zakupie 3 sztuk po 2,49", c["bundle_units"] == 3 and c["single_price"] == 2.49,
                    f"bundle={c['bundle_units']} single={c['single_price']}")
        ok &= check("zakres myślnikiem: 15.09 do 19.09",
                    c["valid_from"] == (15, 9) and c["valid_to"] == (19, 9),
                    f"{c['valid_from']}..{c['valid_to']}")

    print("\nWYNIK:", "wszystko zgodne z gazetką" if ok else "są rozbieżności")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
