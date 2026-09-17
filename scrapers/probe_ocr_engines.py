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

UWAGA o dopasowaniu wyniku, wersja 1: pierwsza wersja tego skryptu liczyła
trafienie przez zwykłe "czy podciąg '199' jest w tekście" — a "199" jest
podciągiem "1199" (cena Raffaello obok masła na tej samej stronie). Wynik
byłby fałszywie dodatni nawet gdyby silnik w ogóle nie zobaczył ceny
masła. Naprawione dopasowaniem na GRANICACH LICZBY.

UWAGA o dopasowaniu wyniku, wersja 2: ta poprawka odsłoniła kolejny,
poważniejszy błąd. PRICE_HINTS to ceny PRZEPISANE Z KONKRETNEJ GAZETKI
("oferta od 10.09"). Biedronka podmienia gazetkę co tydzień — kolejne
uruchomienie tej sondy trafiło już w następną edycję ("oferta od 14.09"),
z innymi promocjami na tej samej pierwszej stronie. Efekt: WSZYSTKIE
silniki, łącznie z EasyOCR, wyszły z zerem trafień — nie dlatego że
przestały czytać, tylko dlatego że szukały cen sprzed tygodnia, których
na tej stronie już nie ma. Sonda z twardą listą wartości jest więc dobra
tylko na tę jedną, konkretną gazetkę, którą miałem przed oczami piszący
ją — nie nadaje się do ponownego uruchomienia bez ręcznej aktualizacji.

Naprawa: PRICE_HINTS zostaje jako opcjonalna podpowiedź (gdy akurat
pasuje — informacyjnie), ale główną miarą jest teraz KSZTAŁT ceny
("dd,dd" albo skleiona 3-4-cyfrowa liczba spoza zakresu lat) — dokładnie
to, co i tak sczytuje find_prices/GLUED_PRICE w prawdziwym pipeline.
Próbka przeczytanego tekstu drukuje się ZAWSZE, nie tylko przy trafieniu,
żeby dało się na oko zweryfikować, czy silnik w ogóle widzi to, co
faktycznie wisi na aktualnej stronie.
"""
import os
import re
import signal
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

# Kształt ceny — nie wartość — bo wartości ze starej gazetki są bez
# znaczenia dla nowej edycji. To ten sam kształt, którego szuka
# find_prices()/GLUED_PRICE w prawdziwym pipeline (flyer_ocr.py):
# "dd,dd" wprost, albo skleiona liczba 3-4-cyfrowa spoza zakresu lat.
PRICE_SHAPE_FULL = re.compile(r'^\d{1,3},\d{2}$')
PRICE_SHAPE_GLUED = re.compile(r'^\d{3,4}$')


def _price_shaped(texts: list[str]) -> list[str]:
    shaped = []
    for t in texts:
        if PRICE_SHAPE_FULL.match(t):
            shaped.append(t)
        elif PRICE_SHAPE_GLUED.match(t) and not 1900 <= int(t) <= 2100:
            shaped.append(t)
    return shaped


def score(name: str, texts: list[str]) -> None:
    """Ile z cen, które NAPRAWDĘ są na tej stronie, silnik odczytał —
    plus, zawsze, próbka surowego tekstu, żeby dało się to zweryfikować
    na oko niezależnie od tego, która edycja gazetki akurat wisi."""
    joined = " ".join(texts)
    hit = sorted(h for h, pattern in _HINT_PATTERNS.items() if pattern.search(joined))
    shaped = _price_shaped(texts)
    print(f"{name:38s} fragmentów={len(texts):4d}  "
          f"trafione_ze_starej_listy={hit}  ksztaltem_ceny={shaped[:20]}")
    print(f"    próbka (pierwsze 50): {' | '.join(texts[:50])[:600]}")


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


class _TimedOut(Exception):
    pass


def _raise_timeout(signum, frame):
    raise _TimedOut()


def try_paddleocr(path: str, budget_s: int = 240) -> None:
    """Cały PaddleOCR (ładowanie modelu + odczyt obu powiększeń) pod
    JEDNYM budżetem czasu.

    Pierwsza próba tego pomiaru zawisła na krok "Install PaddleOCR" +
    inicjalizacji modelu ponad 15 minut bez żadnego wyniku — PaddleOCR
    pobiera wagi modelu przy pierwszym użyciu z bos.bcebos.com (Baidu),
    który bywa bardzo wolny albo niedostępny spoza Chin. To i tak jest
    odpowiedzią wartą zapisania: nawet gdyby sama jakość odczytu była
    lepsza, silnik zależny od wolnego hostingu modeli nie nadaje się do
    pipeline'u, który ma chodzić w CI. Budżet czasu sprawia, że ta sonda
    to STWIERDZA zamiast wisieć w nieskończoność."""
    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        print(f"PaddleOCR niedostępny: {e}")
        return

    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        old_handler = signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(budget_s)

    try:
        # "pl" bywa niedostępny jako osobny model (PaddleOCR grupuje część
        # języków łacińskich pod jednym modelem) — próbujemy po kolei
        # zamiast zgadywać jedną poprawną nazwę.
        ocr = None
        for lang in ("pl", "latin", "en"):
            try:
                try:
                    ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
                except TypeError:
                    ocr = PaddleOCR(use_angle_cls=True, lang=lang)
                print(f"PaddleOCR: model dla lang={lang} załadowany")
                break
            except _TimedOut:
                raise
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
            except _TimedOut:
                raise
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
    except _TimedOut:
        print(f"PaddleOCR: przekroczono budżet {budget_s}s (prawdopodobnie ładowanie "
              f"modelu z bos.bcebos.com) — silnik wykluczony niezależnie od tego, jak "
              f"dobrze czyta, bo pipeline ma chodzić w CI, nie czekać w nieskończoność")
    finally:
        if has_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


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
