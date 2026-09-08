"""
probe_biedronka_ocr.py — jednorazowy skrypt diagnostyczny.

Ustalone dotychczas (patrz probe_biedronka_*.py):
1. https://www.biedronka.pl/pl/gazetki -> linki do aktualnych stron press,id,...
2. Strona press,id,... zawiera w statycznym HTML:
   window.galleryLeaflet.init("{UUID}")
3. https://leaflet-api.prod.biedronka.cloud/api/leaflets/{UUID}?ctx=web
   zwraca images_desktop: [{page, images: [url PNG]}] — same bitmapy,
   ZERO tekstu/hotspotów/cen jako dane.

Więc jedyna droga do prawdziwych cen Biedronki to OCR obrazków stron.
Ten skrypt pobiera JEDNĄ realną stronę gazetki i odpala na niej
Tesseract (darmowy, open-source — użytkownik chce żeby projekt był
darmowy, więc nie płatne API wizyjne), żeby sprawdzić czy tekst w ogóle
da się sensownie odczytać z tej stylizowanej grafiki marketingowej.

Wymaga: apt-get install tesseract-ocr tesseract-ocr-pol (patrz workflow).
"""
import re
import subprocess
import sys

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
UUID_PATTERN = re.compile(r'window\.galleryLeaflet\.init\("([0-9a-f-]{36})"\)')
# Nazewnictwo linków zmienia się co tydzień (np. "-p-" dla sklepów bez lady
# tradycyjnej), a niektóre linki są względne (/pl/press,id,...) a inne
# absolutne (https://www.biedronka.pl/pl/press,id,...) — łapiemy WSZYSTKIE,
# niezależnie od reszty slugu i stylu cudzysłowu.
PRESS_LINK_PATTERN = re.compile(r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\']+)["\']')


def find_current_press_url() -> str:
    resp = requests.get(GAZETKI_URL, headers=HEADERS, timeout=30)
    print(f"[gazetki] status={resp.status_code} bytes={len(resp.content)}")
    candidates = sorted(set(PRESS_LINK_PATTERN.findall(resp.text)))
    print(f"[gazetki] Znalezione linki press,id,... (href=): {len(candidates)}")
    for c in candidates[:20]:
        print(f"  {c}")
    if not candidates:
        # Debug: szukaj samego podciągu "press,id" gdziekolwiek w HTML,
        # niezależnie od stylu cudzysłowu/atrybutu — struktura strony
        # mogła się zmienić między tygodniami.
        idx = resp.text.find("press,id")
        print(f"[debug] 'press,id' w surowym HTML na offset: {idx}")
        if idx != -1:
            print(resp.text[max(0, idx - 300):idx + 300])
        else:
            print("[debug] Pierwsze 3000 znaków strony /pl/gazetki:")
            print(resp.text[:3000])
    if not candidates:
        raise RuntimeError("Nie znaleziono linku do aktualnej gazetki na /pl/gazetki")
    # Preferuj wariant "codziennie-niskie-ceny" (główna gazetka spożywcza),
    # w przeciwnym razie weź pierwszy z brzegu.
    chosen = next((c for c in candidates if "codziennie-niskie-ceny" in c), candidates[0])
    url = "https://www.biedronka.pl" + chosen
    print(f"[gazetki] aktualna gazetka: {url}")
    return url


def find_uuid(press_url: str) -> str:
    resp = requests.get(press_url, headers=HEADERS, timeout=30)
    print(f"[press] status={resp.status_code}")
    m = UUID_PATTERN.search(resp.text)
    if not m:
        raise RuntimeError("Nie znaleziono window.galleryLeaflet.init(...) w HTML strony press")
    uuid = m.group(1)
    print(f"[press] UUID gazetki: {uuid}")
    return uuid


def get_page_images(uuid: str) -> dict:
    """Zwraca {page_index: image_url} dla wszystkich stron gazetki."""
    api_url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
    data = resp.json()
    print(f"[leaflet-api] Liczba stron: {len(data['images_desktop'])}")
    out = {}
    for page in data["images_desktop"]:
        if page["images"]:
            out[page["page"]] = page["images"][0]
    return out


def ocr_page(page_num: int, image_url: str) -> None:
    print(f"\n{'='*70}\nStrona #{page_num} -> {image_url}\n{'='*70}")
    img_resp = requests.get(image_url, headers=HEADERS, timeout=30)
    print(f"[image] status={img_resp.status_code} bytes={len(img_resp.content)}")

    filename = f"test_page_{page_num}.png"
    with open(filename, "wb") as f:
        f.write(img_resp.content)

    # psm 11 (sparse text, bez zakładania układu akapitów) zwykle lepiej
    # radzi sobie z rozrzuconymi cenami/etykietami na grafice marketingowej
    # niż domyślny psm 3 (automatyczna segmentacja stron tekstowych).
    for psm in ("3", "11"):
        print(f"\n[ocr] tesseract --psm {psm} (pol)...")
        result = subprocess.run(
            ["tesseract", filename, "stdout", "-l", "pol", "--psm", psm],
            capture_output=True, text=True,
        )
        if result.stderr.strip():
            print(f"[ocr stderr] {result.stderr[:500]}")
        print(f"-- tekst (psm {psm}) --")
        print(result.stdout)

        price_pattern = re.compile(r'\d{1,3}[,.]\d{2}\b')
        prices_found = price_pattern.findall(result.stdout)
        print(f"[analiza psm {psm}] Wzorce cenowe (X,XX): {prices_found}")


def main():
    press_url = find_current_press_url()
    uuid = find_uuid(press_url)
    pages = get_page_images(uuid)
    print(f"[pages] Dostępne indeksy stron: {sorted(pages.keys())}")

    # Próbujemy kilku stron rozrzuconych po gazetce — strona 1/2 bywa
    # okładką/hero-deal, środkowe strony to zwykle siatka produktów.
    targets = [p for p in (2, 10, 20) if p in pages]
    if not targets:
        targets = list(sorted(pages.keys()))[:3]

    for page_num in targets:
        ocr_page(page_num, pages[page_num])


if __name__ == "__main__":
    main()
