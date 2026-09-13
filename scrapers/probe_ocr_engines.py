"""
probe_ocr_engines.py — czy DOWOLNY darmowy OCR odczyta ceny z gazetki.

Podsumowanie dotychczasowych pomiarów na stronie tytułowej gazetki
"Codziennie niskie ceny" (jedyny dostępny render, 1146x1800):

  skala 0.6x / 1x / 2x, psm 6 / 11 / 12,  alfabet ograniczony do cyfr,
  separacja bieli od koloru, separacja czerni od koloru, autokontrast,
  wycinek kafelka w powiększeniu 1-4x, strona pocięta na 12 nachodzących
  kafelków --- ŻADEN wariant nie odczytał ani jednej wielkiej ceny.

Drobny druk czyta się przy tym bezbłędnie ("PRZY ZAKUPIE 5", "OFERTA OD
10.09 DO 12.09", "Świeży filet z piersi kurczaka"), więc problem nie leży
w rozdzielczości ani w segmentacji strony, tylko w samym kroju: cena to
ciężka, firmowa czcionka z groszami wyniesionymi do góry jak indeks, bez
przecinka, często ze stykającymi się cyframi. Model `pol` tesseracta nie
widział takich kształtów.

Zostały wtedy dwie drogi, obie darmowe i otwartoźródłowe (projekt ma
pozostać bezpłatny, więc płatne API wizyjne odpadają z definicji): inny
silnik z siecią neuronową (EasyOCR — wygrał, patrz leaflet_ocr.py) i
tesseract w silniku "legacy". Ten skrypt dokłada TRZECI kandydat,
PaddleOCR (PP-OCRv4, Apache 2.0), bo padło pytanie, czy jest coś
skuteczniejszego od EasyOCR — a jedyna uczciwa odpowiedź na to pytanie to
pomiar na tej samej stronie, tą samą miarą, a nie zgadywanie z nazwy.

UWAGA o dopasowaniu wyniku: pierwsza wersja tego skrytu liczyła trafienie
przez zwykłe "czy podciąg '199' jest w tekście" — a "199" jest podciągiem
"1199" (cena Raffaello obok masła na tej samej stronie). Wynik byłby
fałszywie dodatni nawet gdyby silnik w ogóle nie zobaczył ceny masła.
Dopasowanie jest teraz na GRANICACH LICZBY (żadna cyfra bezpośrednio przed
ani po), więc "199" nie złapie się na "1199".
"""
import os
import re
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from biedronka.flyers import scrapable_flyers
from flyer_ocr import HEADERS
from biedronka.scraper import find_uuid, get_page_image_urls

PRICE_HINTS = ("1,99", "199", "5,99", "599", "0,99", "099", "11,99", "1199",
               "14,99", "1499", "9,90", "990")


def download_page(slug: str, page_index: int) -> str:
    flyer = next(f for f in scrapable_flyers() if slug in f["slug"])
    urls = get_page_image_urls(find_uuid("https://www.biedronka.pl" + flyer["path"]))
    print(f"{flyer['slug']}: {len(urls)} stron, biorę {page_index}")
    resp = requests.get(urls[page_index], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    path = "/tmp/engine_page.png"
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def _hint_pattern(hint: str) -> re.Pattern:
    """Wzorzec dopasowujący `hint` tylko jako CAŁĄ liczbę — bez cyfry
    bezpośrednio przed ani po, żeby "199" nie łapało się na "1199"."""
    escaped = re.escape(hint)
    return re.compile(rf'(?<!\d)(?<![,.]){escaped}(?![\d,.])')


_HINT_PATTERNS = {h: _hint_pattern(h) for h in PRICE_HINTS}


def score(name: str, texts: list[str]) -> None:
    """Ile z cen, które NAPRAWDĘ są na tej stronie, silnik odczytał."""
    joined = " ".join(texts)
    hit = sorted(h for h, pattern in _HINT_PATTERNS.items() if pattern.search(joined))
    print(f"{name:38s} fragmentów={len(texts):4d}  trafione ceny={hit}")
    if hit:
        print(f"    próbka: {' | '.join(texts[:40])[:400]}")


def try_tesseract(path: str, oem: str, psm: str, upscale: int) -> None:
    image = Image.open(path)
    if upscale != 1:
        image = image.resize((image.width * upscale, image.height * upscale), Image.LANCZOS)
    work = "/tmp/engine_work.png"
    image.save(work)
    try:
        out = subprocess.run(
            ["tesseract", work, "stdout", "-l", "pol", "--oem", oem, "--psm", psm],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        print(f"tesseract oem {oem} psm {psm}: BŁĄD {e}")
        return
    if out.returncode != 0:
        print(f"tesseract oem {oem} psm {psm} {upscale}x: niedostępny "
              f"({out.stderr.strip().splitlines()[-1] if out.stderr.strip() else out.returncode})")
        return
    score(f"tesseract oem{oem} psm{psm} {upscale}x", out.stdout.split())


def try_easyocr(path: str) -> None:
    try:
        import easyocr
    except ImportError as e:
        print(f"EasyOCR niedostępny: {e}")
        return
    reader = easyocr.Reader(["pl"], gpu=False, verbose=False)
    for upscale in (1, 2):
        image = Image.open(path).convert("RGB")
        if upscale != 1:
            image = image.resize((image.width * upscale, image.height * upscale), Image.LANCZOS)
        work = f"/tmp/engine_easy_{upscale}.png"
        image.save(work)
        results = reader.readtext(work, detail=1, paragraph=False)
        texts = [text for _, text, conf in results if conf >= 0.3]
        score(f"EasyOCR {upscale}x", texts)


def try_paddleocr(path: str) -> None:
    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        print(f"PaddleOCR niedostępny: {e}")
        return

    # "pl" bywa niedostępny jako osobny model (PaddleOCR grupuje część
    # języków łacińskich pod jednym modelem) — próbujemy po kolei zamiast
    # zgadywać jedną poprawną nazwę.
    ocr = None
    for lang in ("pl", "latin", "en"):
        try:
            try:
                ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            except TypeError:
                ocr = PaddleOCR(use_angle_cls=True, lang=lang)
            print(f"PaddleOCR: model dla lang={lang} załadowany")
            break
        except Exception as e:
            print(f"PaddleOCR: model dla lang={lang} niedostępny ({e})")
    if ocr is None:
        return

    for upscale in (1, 2):
        image = Image.open(path).convert("RGB")
        if upscale != 1:
            image = image.resize((image.width * upscale, image.height * upscale), Image.LANCZOS)
        work = f"/tmp/engine_paddle_{upscale}.png"
        image.save(work)

        try:
            try:
                result = ocr.ocr(work, cls=True)
            except TypeError:
                result = ocr.ocr(work)
        except Exception as e:
            print(f"PaddleOCR {upscale}x: błąd odczytu ({e})")
            continue

        texts = []
        for page in (result or []):
            for line in (page or []):
                try:
                    text, conf = line[1]
                except Exception:
                    continue
                if conf >= 0.3:
                    texts.append(text)
        score(f"PaddleOCR {upscale}x", texts)


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "codziennie"
    page_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    path = download_page(slug, page_index)
    print(f"szukamy na stronie kwot: {', '.join(PRICE_HINTS)}\n")

    for oem, psm, upscale in (("0", "11", 2), ("0", "6", 2), ("2", "11", 2), ("1", "4", 2)):
        try_tesseract(path, oem, psm, upscale)

    print()
    try_easyocr(path)

    print()
    try_paddleocr(path)


if __name__ == "__main__":
    main()
