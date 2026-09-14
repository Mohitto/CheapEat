"""
probe_flyer_pdf.py — czy gazetka istnieje gdzieś jako PDF Z WARSTWĄ TEKSTU,
a nie tylko jako bitmapy stron.

To pytanie powinno paść PRZED sięgnięciem po jakikolwiek OCR, nie po. Duże
serwisy porównujące gazetki wielu sieci (Blix i podobne) zwykle NIE
prześcigają nas w jakości OCR-u — ich przewaga to najpewniej dane u
źródła: albo prawdziwy PDF z warstwy typografii (skład w InDesign trafia
do publikacji z zachowanym tekstem, zanim ktokolwiek go spłaszczy do
obrazka), albo bezpośrednia umowa z siecią/agencją, która ma listę
produktów i cen jeszcze zanim gazetka zostanie złożona graficznie. Obu
tych dróg nie da się zbudować scraperem — ale WARSTWĘ TEKSTU W PDF-ie da
się, jeśli tylko istnieje. To jest do sprawdzenia zanim uzna się, że OCR
to jedyna droga (dla Biedronki było to już sprawdzone pośrednio —
probe_leaflet_images.py pokazał, że leaflet-api oddaje WYŁĄCZNIE PNG — ale
ten skrypt sprawdza to wprost i zostaje jako wzór dla kolejnego sklepu,
zanim ten w ogóle dostanie scraper oparty o OCR).

Sprawdza dwa miejsca:
  1. Odpowiedź leaflet-api — czy WŚRÓD JEJ KLUCZY (na dowolnym poziomie
     zagnieżdżenia) jest coś, co brzmi jak adres PDF-a.
  2. Surowy HTML strony press,id,... — czy zawiera link kończący się na
     .pdf (przyciski "pobierz gazetkę jako PDF" bywają poza JSON-em
     galerii, w zwykłym linku <a href>).
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from flyer_ocr import HEADERS

PDF_LINK_PATTERN = re.compile(r'https?://[^\s"\'<>]+\.pdf\b', re.IGNORECASE)
PDF_KEY_PATTERN = re.compile(r'pdf', re.IGNORECASE)


def find_pdf_like(obj, path="$") -> list[tuple[str, str]]:
    """(ścieżka, wartość) dla każdego klucza/wartości JSON-a, który
    brzmi jak PDF — rekurencyjnie, bo nie wiadomo, na jakiej głębokości
    API mogłoby to schować."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}"
            if PDF_KEY_PATTERN.search(key) or (isinstance(value, str) and ".pdf" in value.lower()):
                found.append((here, json.dumps(value, ensure_ascii=False)[:200]))
            found.extend(find_pdf_like(value, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):  # próbka, nie cała lista stron
            found.extend(find_pdf_like(item, f"{path}[{i}]"))
    return found


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    flyer = next(f for f in scrapable_flyers() if slug in f["slug"])
    press_url = "https://www.biedronka.pl" + flyer["path"]
    print(f"gazetka: {flyer['slug']}\npress: {press_url}\n")

    print("--- 1. leaflet-api: szukam PDF w JSON-ie ---")
    from biedronka.scraper import find_uuid
    uuid = find_uuid(press_url)
    api_url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    data = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=60).json()
    print(f"klucze najwyższego poziomu: {sorted(data.keys())}")
    hits = find_pdf_like(data)
    if hits:
        print(f"ZNALEZIONO {len(hits)} kandydatów:")
        for path, value in hits:
            print(f"  {path} = {value}")
    else:
        print("brak jakiegokolwiek pola przypominającego PDF w odpowiedzi API")

    print("\n--- 2. strona press,id,...: szukam linku .pdf w HTML ---")
    resp = requests.get(press_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    links = sorted(set(PDF_LINK_PATTERN.findall(resp.text)))
    if links:
        print(f"ZNALEZIONO {len(links)} linków .pdf:")
        for link in links:
            print(f"  {link}")
    else:
        print("brak żadnego linku .pdf w surowym HTML strony")

    print("\nWNIOSEK:", "gazetka ISTNIEJE jako PDF — sprawdź, czy ma warstwę tekstu, zanim cokolwiek OCR-ujesz"
          if hits or links else
          "gazetka NIE jest publikowana jako PDF — OCR obrazków to jedyna droga (już wybrana: EasyOCR)")


if __name__ == "__main__":
    main()
