"""
probe_ocr_settings.py — które ustawienia OCR realnie zwiększają odczyt gazetki?

probe_flyer_layout.py pokazał, że dopasowanie ceny do nazwy po
współrzędnych działa, ale tesseract widzi tylko ~64 słowa na całej
stronie gazetki — i to jest prawdziwe wąskie gardło, nie logika
dopasowania. Strona gazetki to plakat: duże, stylizowane napisy na
kolorowym tle, w wielu kolumnach.

Porównujemy na tych samych stronach:
  - tryby segmentacji: 3 (auto), 6 (jednolity blok), 11 (rzadki tekst),
  - skalę: 1x i 2x (upscaling zwykle mocno pomaga na plakatach),
liczbą rozpoznanych słów, tokenów cenowych i słów kluczowych.

Nic nie zapisuje do bazy.
"""
import os
import re
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingredient_catalog import INGREDIENT_KEYWORDS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
PRESS_LINK_PATTERN = re.compile(r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\']+)["\']')
UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')
PRICE_TOKEN = re.compile(r'^\d{1,3}[,.]\d{2}$')

ALL_KEYWORDS = [kw for kws in INGREDIENT_KEYWORDS.values() for kw in kws]

# Gazetka, która NAS interesuje na tym teście: festiwal nabiału (masło!).
PREFERRED_SLUGS = ["festiwal-nabiau", "codziennie-niskie-ceny-p-oferta-od-07-09"]
PAGES_TO_TEST = [2, 3, 4]


def find_flyers() -> list[str]:
    resp = requests.get(GAZETKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    seen, out = set(), []
    for m in PRESS_LINK_PATTERN.finditer(resp.text):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def page_urls(press_path: str) -> list[str]:
    resp = requests.get("https://www.biedronka.pl" + press_path, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    m = UUID_PATTERN.search(resp.text)
    if not m:
        return []
    api = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{m.group(1)}?ctx=web"
    data = requests.get(api, headers={**HEADERS, "Accept": "application/json"}, timeout=30).json()
    urls = []
    for p in data.get("images_desktop", []):
        for img in p.get("images", []):
            if img:
                urls.append(img)
                break
    return urls


def run_ocr(path: str, psm: int) -> list[str]:
    out = subprocess.run(
        ["tesseract", path, "stdout", "-l", "pol", "--psm", str(psm), "tsv"],
        capture_output=True, text=True, timeout=180,
    ).stdout
    words = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        if text and conf >= 40:
            words.append(text)
    return words


def score(words: list[str]) -> tuple[int, int, int]:
    prices = sum(1 for w in words if PRICE_TOKEN.match(w))
    joined = " ".join(words).lower()
    kws = sum(1 for kw in ALL_KEYWORDS if kw in joined)
    return len(words), prices, kws


def main():
    flyers = find_flyers()
    chosen = None
    for slug in PREFERRED_SLUGS:
        chosen = next((f for f in flyers if slug in f), None)
        if chosen:
            break
    if not chosen:
        chosen = flyers[0]
    print(f"Gazetka testowa: {chosen}")

    urls = page_urls(chosen)
    print(f"Stron: {len(urls)}\n")

    for page_idx in PAGES_TO_TEST:
        if page_idx >= len(urls):
            continue
        raw = requests.get(urls[page_idx], headers=HEADERS, timeout=60).content
        base = f"/tmp/page_{page_idx}.png"
        with open(base, "wb") as f:
            f.write(raw)

        img = Image.open(base)
        print(f"=== Strona {page_idx}: obraz {img.width}x{img.height} ===")

        variants = [("1x", base)]
        up = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        up_path = f"/tmp/page_{page_idx}_2x.png"
        up.save(up_path)
        variants.append(("2x", up_path))

        grey_path = f"/tmp/page_{page_idx}_2x_grey.png"
        up.convert("L").point(lambda p: 255 if p > 160 else 0).save(grey_path)
        variants.append(("2x+próg", grey_path))

        for scale_name, path in variants:
            for psm in (3, 6, 11):
                try:
                    words = run_ocr(path, psm)
                except subprocess.TimeoutExpired:
                    print(f"  {scale_name:8s} psm={psm:<3} TIMEOUT")
                    continue
                n, prices, kws = score(words)
                print(f"  {scale_name:8s} psm={psm:<3} słów={n:<5} cen={prices:<4} słów kluczowych={kws}")
        print()


if __name__ == "__main__":
    main()
