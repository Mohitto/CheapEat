"""
probe_leaflet_images.py — czy leaflet-api oddaje stronę w większej
rozdzielczości, i czy cena da się odczytać z powiększonego wycinka.

Dwanaście wariantów przygotowania obrazu (probe_ocr_variants.py) nie
odczytało ze strony tytułowej ANI JEDNEJ wielkiej ceny, a drobny druk
czytało bez trudu. To każe podejrzewać nie ustawienia OCR, tylko materiał
wejściowy: strona przychodzi jako 1146x1800 px na całą kartkę, a scraper
bierze PIERWSZY niepusty adres z listy `images`, nie sprawdzając nawet,
czy w tej liście nie ma większego renderu.

Ten skrypt sprawdza jedno i drugie:
  1. wypisuje surową strukturę odpowiedzi API dla kilku pierwszych stron
     wraz z realnym rozmiarem każdego wariantu obrazka,
  2. bierze największy dostępny, wycina okolicę ceny i próbuje ją
     odczytać w kilku powiększeniach — jeśli cena czyta się z wycinka,
     problemem jest rozdzielczość/segmentacja strony, a nie sam krój.
"""
import json
import os
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from biedronka.leaflet_ocr import HEADERS
from biedronka.scraper import find_uuid


def api_payload(flyer: dict) -> dict:
    uuid = find_uuid("https://www.biedronka.pl" + flyer["path"])
    url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def measure(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        path = "/tmp/leaflet_measure.png"
        with open(path, "wb") as f:
            f.write(resp.content)
        image = Image.open(path)
        return f"{image.width}x{image.height}, {len(resp.content) // 1024} kB"
    except Exception as e:
        return f"nie pobrano ({e})"


def ocr_text(image: Image.Image, psm: str) -> str:
    path = "/tmp/leaflet_crop.png"
    image.save(path)
    out = subprocess.run(
        ["tesseract", path, "stdout", "-l", "pol", "--psm", psm],
        capture_output=True, text=True, timeout=120,
    ).stdout
    return " ".join(out.split())


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    flyer = next(f for f in scrapable_flyers() if slug in f["slug"])
    print(f"gazetka: {flyer['slug']}")

    data = api_payload(flyer)
    print(f"klucze odpowiedzi: {sorted(data.keys())}\n")

    for key in ("images_desktop", "images_mobile", "images"):
        pages = data.get(key)
        if not isinstance(pages, list) or not pages:
            continue
        print(f"--- {key}: {len(pages)} pozycji, pierwsza pozycja w całości ---")
        print(json.dumps(pages[0], ensure_ascii=False, indent=2)[:1500])
        print()

    pages = data["images_desktop"]
    print("--- REALNE ROZMIARY WARIANTÓW STRONY 0 ---")
    urls = [u for u in pages[0].get("images", []) if u]
    for i, url in enumerate(urls):
        print(f"  [{i}] {measure(url)}  {url[:110]}")
    if not urls:
        print("  brak adresów")
        return

    # Największy wariant, jaki API daje — i tak zwykle będzie to ostatni,
    # ale sprawdzamy realnie, zamiast zakładać kolejność.
    best_url, best_pixels, best_image = None, 0, None
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            path = "/tmp/leaflet_best.png"
            with open(path, "wb") as f:
                f.write(resp.content)
            image = Image.open(path).convert("RGB")
        except Exception:
            continue
        if image.width * image.height > best_pixels:
            best_url, best_pixels, best_image = url, image.width * image.height, image

    print(f"\nnajwiększy: {best_image.width}x{best_image.height}  {best_url[:110]}")

    # Kafelek masła leży w prawej górnej ćwiartce strony (patrz gazetka:
    # "MASŁO ekstra" tuż pod znaczkiem "PRZY ZAKUPIE 5").
    w, h = best_image.width, best_image.height
    crop = best_image.crop((int(w * 0.47), int(h * 0.12), int(w * 0.72), int(h * 0.33)))
    print(f"wycinek kafelka masła: {crop.width}x{crop.height}")

    for factor in (1, 2, 3, 4):
        scaled = crop if factor == 1 else crop.resize(
            (crop.width * factor, crop.height * factor), Image.LANCZOS)
        for psm in ("6", "7", "11"):
            print(f"  x{factor} psm {psm}: {ocr_text(scaled, psm)[:160]}")


if __name__ == "__main__":
    main()
