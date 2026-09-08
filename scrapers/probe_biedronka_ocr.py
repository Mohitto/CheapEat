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
PRESS_LINK_PATTERN = re.compile(r'href="(/pl/press,id,[^"]+codziennie-niskie-ceny-p[^"]*)"')


def find_current_press_url() -> str:
    resp = requests.get(GAZETKI_URL, headers=HEADERS, timeout=30)
    print(f"[gazetki] status={resp.status_code}")
    m = PRESS_LINK_PATTERN.search(resp.text)
    if not m:
        # fallback: dowolny link press,id,...
        m = re.search(r'href="(/pl/press,id,[^"]+)"', resp.text)
    if not m:
        raise RuntimeError("Nie znaleziono linku do aktualnej gazetki na /pl/gazetki")
    url = "https://www.biedronka.pl" + m.group(1)
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


def get_first_page_image(uuid: str) -> str:
    api_url = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web"
    resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
    data = resp.json()
    # strona 1 (page index 1, bo page 0 bywa pusta okładka wg wcześniejszej sondy)
    for page in data["images_desktop"]:
        if page["page"] == 1 and page["images"]:
            return page["images"][0]
    # fallback: pierwsza strona z jakimkolwiek obrazkiem
    for page in data["images_desktop"]:
        if page["images"]:
            return page["images"][0]
    raise RuntimeError("Brak obrazków stron w odpowiedzi leaflet-api")


def main():
    press_url = find_current_press_url()
    uuid = find_uuid(press_url)
    image_url = get_first_page_image(uuid)
    print(f"\n[image] pobieram: {image_url}")

    img_resp = requests.get(image_url, headers=HEADERS, timeout=30)
    print(f"[image] status={img_resp.status_code} bytes={len(img_resp.content)}")

    with open("test_page.png", "wb") as f:
        f.write(img_resp.content)

    print("\n[ocr] uruchamiam tesseract (pol+eng)...")
    result = subprocess.run(
        ["tesseract", "test_page.png", "stdout", "-l", "pol"],
        capture_output=True, text=True,
    )
    print(f"[ocr] returncode={result.returncode}")
    if result.stderr:
        print(f"[ocr stderr] {result.stderr[:1000]}")

    print("\n" + "=" * 70)
    print("SUROWY TEKST Z OCR:")
    print("=" * 70)
    print(result.stdout)

    # Szukaj wzorców cenowych w wyniku OCR
    price_pattern = re.compile(r'\d{1,3}[,.]\d{2}')
    prices_found = price_pattern.findall(result.stdout)
    print(f"\n[analiza] Znalezione wzorce cenowe (X,XX): {prices_found}")


if __name__ == "__main__":
    main()
