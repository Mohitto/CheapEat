"""
probe_flyer_layout.py — jak cena leży na stronie gazetki względem nazwy?

Obecny parser (biedronka/scraper.py) czyta OCR jako JEDEN ciąg tekstu i
szuka nazwy składnika w oknie ~200 znaków przed ceną. Na gazetce, która
jest siatką kafelków, kolejność czytania nie odpowiada układowi
graficznemu: cena bywa oddzielona od swojej nazwy setkami znaków innego
kafelka. Dlatego z 52 stron wyciągnęliśmy ceny tylko dla 2 składników.

Ta sonda sprawdza hipotezę, że trzeba dopasowywać PRZESTRZENNIE:
tesseract w trybie TSV zwraca ramkę (left/top/width/height) i pewność
dla każdego słowa. Wypisujemy:
  1. wszystkie gazetki ogłoszone na /pl/gazetki wraz z datami obok linku
     (potrzebne do śledzenia nowych i wygasania starych),
  2. dla kilku stron: tokeny cenowe z ramkami i wysokością fontu
     (duża czcionka = główna cena promocyjna, mała = cena jednostkowa),
  3. dla każdej ceny — najbliższe przestrzennie słowo kluczowe składnika,
     czyli dokładnie to, czym chcemy zastąpić okno znakowe.

Nie zapisuje niczego do bazy.
"""
import os
import re
import subprocess
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingredient_catalog import INGREDIENT_KEYWORDS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
PRESS_LINK_PATTERN = re.compile(r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\']+)["\']')
UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')
DATE_RANGE_PATTERN = re.compile(r'(\d{1,2}[.-]\d{1,2}(?:[.-]\d{2,4})?)\s*[-–—]\s*(\d{1,2}[.-]\d{1,2}(?:[.-]\d{2,4})?)')

PRICE_TOKEN = re.compile(r'^\d{1,3}[,.]\d{2}$')
BARE_NUMBER = re.compile(r'^\d{1,3}$')

MAX_PAGES_TO_SCAN = 14
MAX_PAGES_TO_REPORT = 3


def list_flyers() -> list[dict]:
    """Wszystkie gazetki ogłoszone na stronie, z tekstem wokół linku —
    stamtąd trzeba będzie wyciągać zakres dat obowiązywania."""
    resp = requests.get(GAZETKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    flyers = []
    for m in PRESS_LINK_PATTERN.finditer(html):
        path = m.group(1)
        around = html[max(0, m.start() - 700): m.end() + 700]
        text = re.sub(r'<[^>]+>', ' ', around)
        text = re.sub(r'\s+', ' ', text).strip()
        dates = DATE_RANGE_PATTERN.findall(text)
        flyers.append({"path": path, "dates": dates[:3], "context": text[:220]})

    # deduplikacja po ścieżce, zachowując kolejność
    seen, unique = set(), []
    for f in flyers:
        if f["path"] in seen:
            continue
        seen.add(f["path"])
        unique.append(f)
    return unique


def get_page_image_urls(press_path: str) -> list[str]:
    resp = requests.get("https://www.biedronka.pl" + press_path, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    m = UUID_PATTERN.search(resp.text)
    if not m:
        print(f"  [!] brak UUID na {press_path}")
        return []
    uuid = m.group(1)
    api = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    data = requests.get(api, headers={**HEADERS, "Accept": "application/json"}, timeout=30).json()
    urls = []
    for p in data.get("images_desktop", []):
        for img in p.get("images", []):
            if img:
                urls.append(img)
                break
    return urls


def ocr_tokens(image_url: str) -> list[dict]:
    """Słowa z OCR wraz z ramkami (tesseract TSV) — bez dodatkowych zależności."""
    img = requests.get(image_url, headers=HEADERS, timeout=30)
    img.raise_for_status()
    path = "/tmp/flyer_page.png"
    with open(path, "wb") as f:
        f.write(img.content)

    out = subprocess.run(
        ["tesseract", path, "stdout", "-l", "pol", "--psm", "3", "tsv"],
        capture_output=True, text=True, timeout=120,
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
        if conf < 40:
            continue
        tokens.append({
            "text": text,
            "left": int(parts[6]), "top": int(parts[7]),
            "width": int(parts[8]), "height": int(parts[9]),
            "conf": conf,
        })
    return tokens


def centre(t: dict) -> tuple[float, float]:
    return t["left"] + t["width"] / 2, t["top"] + t["height"] / 2


def analyse_page(index: int, tokens: list[dict]) -> None:
    prices = [t for t in tokens if PRICE_TOKEN.match(t["text"])]
    keywords = []
    for t in tokens:
        low = t["text"].lower().strip(",.:;")
        for name, kws in INGREDIENT_KEYWORDS.items():
            if any(low == kw or (len(low) > 4 and low in kw) or (len(kw) > 4 and kw in low) for kw in kws):
                keywords.append({**t, "ingredient": name})
                break

    print(f"\n--- Strona {index}: {len(tokens)} słów, {len(prices)} tokenów cenowych, "
          f"{len(keywords)} słów kluczowych ---")

    heights = sorted({p["height"] for p in prices})
    print(f"  wysokości fontu cen: {heights}")

    for p in prices[:14]:
        px, py = centre(p)
        best, best_d = None, None
        for k in keywords:
            kx, ky = centre(k)
            d = ((px - kx) ** 2 + (py - ky) ** 2) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = k, d
        if best is None:
            print(f"  {p['text']:>8}  h={p['height']:>3}  -> brak słowa kluczowego na stronie")
        else:
            print(f"  {p['text']:>8}  h={p['height']:>3} @({p['left']},{p['top']})"
                  f"  -> najbliżej '{best['text']}' ({best['ingredient']}) "
                  f"@({best['left']},{best['top']}), odległość {best_d:.0f}px")


def main():
    print("=== 1. Gazetki ogłoszone na /pl/gazetki ===")
    flyers = list_flyers()
    for f in flyers:
        print(f"  {f['path']}")
        print(f"      daty w otoczeniu: {f['dates']}")
        print(f"      kontekst: {f['context'][:160]}")

    if not flyers:
        print("Brak gazetek — koniec.")
        return

    chosen = next((f for f in flyers if "codziennie-niskie-ceny" in f["path"]), flyers[0])
    print(f"\n=== 2. Analiza układu strony dla {chosen['path']} ===")

    urls = get_page_image_urls(chosen["path"])
    print(f"  stron w gazetce: {len(urls)}")

    reported = 0
    for i, url in enumerate(urls[:MAX_PAGES_TO_SCAN]):
        try:
            tokens = ocr_tokens(url)
        except Exception as e:
            print(f"  strona {i}: błąd OCR ({e})")
            continue

        has_price = any(PRICE_TOKEN.match(t["text"]) for t in tokens)
        has_kw = any(
            any(kw in t["text"].lower() for kws in INGREDIENT_KEYWORDS.values() for kw in kws)
            for t in tokens
        )
        if not (has_price and has_kw):
            continue

        analyse_page(i, tokens)
        reported += 1
        if reported >= MAX_PAGES_TO_REPORT:
            break


if __name__ == "__main__":
    main()
