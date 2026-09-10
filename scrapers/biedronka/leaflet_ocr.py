"""
leaflet_ocr.py — odczyt cen ze stron gazetki po UKŁADZIE GRAFICZNYM.

Poprzednie podejście spłaszczało stronę do jednego ciągu tekstu i szukało
nazwy składnika w oknie ~200 znaków przed ceną. Strona gazetki to jednak
siatka kafelków, a kolejność czytania OCR nie odpowiada układowi: cena
bywa oddzielona od swojej nazwy setkami znaków z sąsiedniego kafelka.
Efekt: z 52 stron wyciągaliśmy ceny dla 2 składników.

Tutaj korzystamy z tego, że tesseract w trybie TSV podaje ramkę każdego
słowa, więc cenę wiążemy z nazwą po ODLEGŁOŚCI NA STRONIE. Zmierzone na
prawdziwej gazetce (probe_flyer_layout.py): cena "4,59" leżała 116 px pod
napisem "Olej rzepakowy", w odległości 156 px — relacja jest wyraźna.

Ustawienia OCR też są zmierzone, nie zgadnięte (probe_ocr_settings.py,
strona produktowa gazetki):
    psm 3  (obecne), 1x -> 137 słów, 5 cen
    psm 11,          1x -> 169 słów, 8 cen
    psm 11,          2x -> 202 słowa, 9 cen   <- wybrane
Powiększenie 2x i tryb "rzadkiego tekstu" dają ~+50% słów i ~+80% cen.

DWA SILNIKI, I TO NIE Z KAPRYSU
-------------------------------
Tesseract NIE odczytuje cen z gazetki Biedronki. Nie "słabo" — wcale.
Zmierzone na stronie tytułowej (probe_ocr_variants.py, probe_page_tiles.py,
probe_leaflet_images.py), gdzie wydrukowane są masło 1,99, papryka 5,99 i
filet 14,99:

    skala 0.6x / 1x / 2x .................. 0 cen
    psm 6 / 11 / 12 ....................... 0 cen
    alfabet ograniczony do cyfr ........... rozpada się segmentacja
    separacja bieli od koloru ............. 0 cen
    separacja czerni od koloru ............ 0 cen
    autokontrast .......................... 1 cena (drobna plakietka zł/kg)
    wycinek kafelka w 1-4x ................ 0 cen
    12 nachodzących kafelków w 3x ......... 0 cen
    silnik legacy (--oem 0) ............... 0 cen
    EasyOCR, 2x ........................... 1,99 5,99 9,90 11,99 14,99 0,99

Ten sam obrazek oddaje przy tym drobny druk co do znaku. Nie chodzi więc
o rozdzielczość (API daje jeden rozmiar, 1146x1800) ani o układ strony,
tylko o KRÓJ: cena to ciężka firmowa czcionka, grosze wyniesione jak
indeks górny, bez przecinka, cyfry często się stykają. Model `pol` takich
kształtów nie widział, sieć EasyOCR radzi sobie z nimi bez trudu.

EasyOCR jest jednak ~15x wolniejszy, a gazetka ma prawie sto stron. Stąd
podział ról: tesseract przegląda WSZYSTKIE strony i mówi tanio, czy jest
na nich w ogóle nazwa któregoś z naszych składników; EasyOCR czyta tylko
te strony, na których coś jest. Oba silniki są darmowe i otwartoźródłowe
— projekt ma pozostać bezpłatny, więc płatne API wizyjne odpadają z
definicji, nie z braku pomysłu.
"""
import os
import re
import subprocess
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingredient_catalog import (
    fold,
    fuzzy_ingredient,
    is_plausible,
    unit_for,
    unit_price_of,
)

OCR_PSM = "11"          # sparse text — strona gazetki to plakat, nie akapit
OCR_UPSCALE = 2         # duże, stylizowane napisy czytają się lepiej powiększone
MIN_CONFIDENCE = 40

# Cena na gazetce bywa złożona z dwóch tokenów ("5" i "99" obok siebie,
# bo grosze są mniejszą czcionką), więc oprócz pełnej ceny zbieramy też
# same liczby i sklejamy je w PRICE_MAX_PART_GAP pikselach od siebie.
FULL_PRICE = re.compile(r'^(\d{1,3})[,.](\d{2})$')
INTEGER_PART = re.compile(r'^\d{1,3}$')
DECIMAL_PART = re.compile(r'^\d{2}$')

# Gazetka składa cenę z dużych złotówek i małych, uniesionych groszy —
# bez przecinka między nimi. OCR widzi to jako jedną liczbę: "349" zamiast
# "3,49", "1099" zamiast "10,99". Bez tego większość cen promocyjnych w
# ogóle do nas nie docierała (85 stron dawało 4 składniki).
GLUED_PRICE = re.compile(r'^\d{3,4}$')
# Token tuż za ceną, który zdradza, że to była gramatura, a nie kwota.
UNIT_AFTER_NUMBER = re.compile(r'^(g|ml|kg|l|szt\.?|%)$', re.IGNORECASE)
# Duża czcionka to podstawowy sygnał, że liczba jest ceną z kafelka, a nie
# wagą w drobnym druku; próg liczony względem mediany strony.
GLUED_PRICE_MIN_HEIGHT_RATIO = 1.3
GLUED_PRICE_MIN_MAX_RATIO = 0.45

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}


class Token:
    __slots__ = ("text", "left", "top", "width", "height", "conf")

    def __init__(self, text: str, left: int, top: int, width: int, height: int, conf: float):
        self.text = text
        self.left, self.top, self.width, self.height = left, top, width, height
        self.conf = conf

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2

    def distance_to(self, other: "Token") -> float:
        return ((self.cx - other.cx) ** 2 + (self.cy - other.cy) ** 2) ** 0.5

    def __repr__(self) -> str:
        return f"Token({self.text!r} @({self.left},{self.top}) h={self.height})"


_last_download: tuple[str, str] | None = None


def _download_page(image_url: str) -> Image.Image:
    """Strona z dysku, jeśli to ta sama, którą przed chwilą pobraliśmy.

    Każdą interesującą stronę czytamy dwoma silnikami po kolei, a strony
    gazetki ważą po ~2,5 MB — bez tego cała gazetka szłaby przez sieć
    dwa razy."""
    global _last_download
    raw_path = "/tmp/leaflet_page_raw.png"
    if _last_download and _last_download[0] == image_url:
        return Image.open(_last_download[1])

    resp = requests.get(image_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    with open(raw_path, "wb") as f:
        f.write(resp.content)
    _last_download = (image_url, raw_path)
    return Image.open(raw_path)


def ocr_page(image_url: str, timeout: int = 120) -> tuple[list[Token], int]:
    """Słowa strony gazetki z ramkami. Zwraca (tokeny, szerokość strony)."""
    image = _download_page(image_url)
    scaled = image.resize((image.width * OCR_UPSCALE, image.height * OCR_UPSCALE), Image.LANCZOS)
    ocr_path = "/tmp/leaflet_page_ocr.png"
    scaled.save(ocr_path)

    out = subprocess.run(
        ["tesseract", ocr_path, "stdout", "-l", "pol", "--psm", OCR_PSM, "tsv"],
        capture_output=True, text=True, timeout=timeout,
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
        if conf < MIN_CONFIDENCE:
            continue
        tokens.append(Token(text, int(parts[6]), int(parts[7]),
                            int(parts[8]), int(parts[9]), conf))

    return tokens, scaled.width


EASYOCR_UPSCALE = 2
EASYOCR_MIN_CONFIDENCE = 0.3
_easyocr_reader = None


def _reader():
    """Model EasyOCR wczytywany raz na proces — jego budowa trwa dłużej
    niż odczyt pojedynczej strony."""
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(["pl"], gpu=False, verbose=False)
    return _easyocr_reader


def _split_fragment(text: str, left: int, top: int, width: int,
                    height: int, conf: float) -> list[Token]:
    """EasyOCR zwraca całe frazy ("PRZY ZAKUPIE 5"), a cała reszta tego
    pliku pracuje na pojedynczych słowach z własną ramką. Dzielimy ramkę
    frazy proporcjonalnie do długości słów — przybliżenie, ale w zupełności
    wystarczające, bo używamy tych współrzędnych do liczenia ODLEGŁOŚCI
    między słowem a ceną, a nie do przycinania obrazu."""
    words = text.split()
    if len(words) <= 1:
        return [Token(text.strip(), left, top, width, height, conf)]

    units = sum(len(w) for w in words) + (len(words) - 1)
    tokens, x = [], float(left)
    for word in words:
        span = width * len(word) / units
        tokens.append(Token(word, int(x), top, max(1, int(span)), height, conf))
        x += width * (len(word) + 1) / units
    return tokens


def ocr_page_precise(image_url: str) -> tuple[list[Token], int]:
    """Odczyt strony silnikiem, który radzi sobie z cenami (EasyOCR).

    Zwraca to samo co ocr_page — (tokeny, szerokość strony) — więc reszta
    pipeline'u nie wie, którym silnikiem czytano."""
    image = _download_page(image_url).convert("RGB")
    scaled = image.resize((image.width * EASYOCR_UPSCALE, image.height * EASYOCR_UPSCALE),
                          Image.LANCZOS)
    path = "/tmp/leaflet_page_easyocr.png"
    scaled.save(path)

    tokens: list[Token] = []
    for box, text, conf in _reader().readtext(path, detail=1, paragraph=False):
        if conf < EASYOCR_MIN_CONFIDENCE or not text.strip():
            continue
        xs = [int(point[0]) for point in box]
        ys = [int(point[1]) for point in box]
        tokens.extend(_split_fragment(
            text, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), conf * 100))

    return tokens, scaled.width


def find_prices(tokens: list[Token], page_width: int) -> list[tuple[Token, float]]:
    """Tokeny wyglądające na cenę, wraz z kwotą. Obsługuje też ceny
    rozbite na dwa tokeny ("5" obok "99"), bo grosze bywają mniejszą
    czcionką i tesseract rozdziela je na osobne słowa."""
    found: list[tuple[Token, float]] = []
    used: set[int] = set()

    for i, t in enumerate(tokens):
        m = FULL_PRICE.match(t.text)
        if m and not _is_date(t, tokens, page_width):
            found.append((t, float(f"{m.group(1)}.{m.group(2)}")))
            used.add(i)

    max_gap = page_width * 0.04
    for i, t in enumerate(tokens):
        if i in used or not INTEGER_PART.match(t.text):
            continue
        for j, other in enumerate(tokens):
            if j == i or j in used or not DECIMAL_PART.match(other.text):
                continue
            # Grosze stoją tuż obok złotówek i mniej więcej na tej samej
            # wysokości; wykluczamy przypadkowe pary z innych kafelków.
            if other.left < t.left or other.left - (t.left + t.width) > max_gap:
                continue
            if abs(other.top - t.top) > t.height:
                continue
            found.append((t, float(f"{t.text}.{other.text}")))
            used.add(i)
            used.add(j)
            break

    found.extend(_find_glued_prices(tokens, used, page_width))
    return found


# Daty na gazetce wyglądają dokładnie jak ceny: "OFERTA OD 10.09 DO
# 12.09" to dla wzorca ceny dwie kwoty, 10,09 zł i 12,09 zł. Brane za
# ceny trafiały do bazy jako całkiem wiarygodne (masło 10,09 zł za 200 g
# mieści się w każdym rozsądnym zakresie), więc żadna kontrola dalej ich
# nie łapała — jedyne miejsce, gdzie widać różnicę, to sąsiedztwo słów
# "od"/"do"/"oferta".
# Separator bywa i kropką, i przecinkiem — EasyOCR czyta "OD 10.09" jako
# "OD 10,09". Za to sąsiadem musi być "do" albo "oferta": samo "od"
# odrzucałoby prawdziwe ceny z gazetkowego "już od 9,99".
DATE_LIKE = re.compile(r'^(\d{1,2})[.,](\d{2})$')
DATE_NEIGHBOURS = {"do", "oferta", "-"}


def _is_date(token: Token, tokens: list[Token], page_width: int) -> bool:
    m = DATE_LIKE.match(token.text)
    if not m or not 1 <= int(m.group(2)) <= 12:
        return False

    max_gap = page_width * 0.06
    for other in tokens:
        if other is token:
            continue
        if abs(other.cy - token.cy) > token.height:
            continue
        gap = max(other.left - (token.left + token.width),
                  token.left - (other.left + other.width))
        if gap > max_gap:
            continue
        if (fold(other.text.strip(".,"), ocr_digits=False) in DATE_NEIGHBOURS
                or DATE_LIKE.match(other.text)):
            return True
    return False


# "66% TANIEJ" — po liczbie stoi słowo "taniej", więc to rabat, nie kwota.
# Wzorzec dopuszcza "tanlej", bo fold() zamienia wielkie "I" na "l"
# (w bezszeryfowym foncie to ta sama kreska) — bez tego strażnik nie
# łapał niczego, co przyszło z gazetki zapisane wersalikami.
TANIEJ = re.compile(r'^tan[il]e[jl]', re.IGNORECASE)


def _followed_by_taniej(token: Token, tokens: list[Token], page_width: int) -> bool:
    max_gap = page_width * 0.06
    for other in tokens:
        if other is token or not TANIEJ.match(fold(other.text, ocr_digits=False)):
            continue
        if other.left < token.left:
            continue
        if other.left - (token.left + token.width) > max_gap:
            continue
        if abs(other.cy - token.cy) > token.height:
            continue
        return True
    return False


def _find_glued_prices(tokens: list[Token], used: set[int],
                       page_width: int) -> list[tuple[Token, float]]:
    """Ceny zapisane bez przecinka ("349" = 3,49 zł), bo złotówki i grosze
    mają różną wielkość i OCR łączy je w jedną liczbę.

    Sama liczba to za mało, żeby uznać ją za cenę — "400" bywa gramaturą,
    a "2026" rokiem. Wymagamy więc dużej czcionki (cena jest jednym z
    największych napisów na kafelku) i braku jednostki tuż obok."""
    heights = sorted(t.height for t in tokens)
    if not heights:
        return []
    median_height = heights[len(heights) // 2]
    # Dwa progi naraz: "wyraźnie większe od zwykłego tekstu" ORAZ "w skali
    # największych napisów strony". Sama mediana zawodzi na stronach z
    # garstką tokenów, gdzie i ona jest duża; sam udział w maksimum
    # przepuszczałby drobny druk na stronach bez dużych nagłówków.
    min_height = max(median_height * GLUED_PRICE_MIN_HEIGHT_RATIO,
                     heights[-1] * GLUED_PRICE_MIN_MAX_RATIO)
    max_gap = page_width * 0.02

    out: list[tuple[Token, float]] = []
    for i, t in enumerate(tokens):
        if i in used or not GLUED_PRICE.match(t.text):
            continue
        if t.height < min_height:
            continue

        value = int(t.text)
        # Lata (1900-2100) zapisane bez separatora wyglądają identycznie
        # jak cena rzędu 19-21 zł, a w gazetce pełno dat.
        if 1900 <= value <= 2100:
            continue

        # Wielkość rabatu jest na gazetce równie duża jak cena, a znak
        # procenta bywa odczytany jako dziewiątka ("66% TANIEJ" -> "669
        # TANIEJ"). Bez tego z każdej plakietki rabatu robiła się cena.
        if _followed_by_taniej(t, tokens, page_width):
            continue

        if any(
            UNIT_AFTER_NUMBER.match(other.text)
            and other.left >= t.left
            and other.left - (t.left + t.width) <= max_gap
            and abs(other.top - t.top) <= t.height
            for other in tokens
        ):
            continue

        out.append((t, value / 100))

    return out


# Cena z dopiskiem "/kg", "/l", "/100 g" to cena JEDNOSTKOWA podana obok
# ceny opakowania — nie wolno jej wziąć za kwotę do zapłaty. OCR skleja
# ten dopisek na różne sposoby ("zł/kg", "zl/kg", "/kg", "kg"), a bywa i
# tak, że cała cena jednostkowa wychodzi jednym tokenem ("199,50zł/kg"),
# stąd dwa wzorce zamiast jednego.
# Tylko formy z ukośnikiem: samo "kg"/"l" obok ceny bywa gramaturą
# produktu ("1 kg"), a OCR myli "1" z "l", więc bez ukośnika łatwo
# uznalibyśmy zwykłą cenę opakowania za cenę za kilogram.
UNIT_PRICE_SUFFIX = re.compile(r'^(z[łl])?\s*/\s*(kg|l|szt|100)\b', re.IGNORECASE)
UNIT_PRICE_INLINE = re.compile(r'\d\s*(z[łl])?\s*/\s*(kg|l|szt|100)\b', re.IGNORECASE)
# Gramatura jako jeden token ("500g") albo dwa ("500" + "g").
SPEC_ONE_TOKEN = re.compile(r'^(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|szt)\.?$', re.IGNORECASE)
SPEC_NUMBER = re.compile(r'^\d+(?:[.,]\d+)?$')
# "200 g" wychodzi z OCR jako "2009" — litera "g" w tym kroju jest niemal
# nieodróżnialna od dziewiątki, a bez gramatury cała oferta wypada
# ("brak gramatury w pobliżu"). Ograniczenia trzymają to blisko ziemi:
# gramatury opakowań są wielokrotnościami dziesięciu, więc cena odczytana
# jako "1499" czy "199" tu nie wpadnie.
SPEC_GRAMS_AS_NINE = re.compile(r'^(\d{2,4})9$')
SPEC_UNIT = re.compile(r'^(kg|g|ml|l|szt)\.?$', re.IGNORECASE)

MAX_NAME_DISTANCE_RATIO = 0.22   # ułamek szerokości strony
# Gramatura stoi na końcu opisu produktu ("Masło Ekstra z Polskiej
# Mleczarni, 200 g"), więc od wielkiej ceny nad opisem dzieli ją cała
# szerokość tego opisu — przy 0.18 realny kafelek masła z pierwszej
# strony gazetki wypadał jako "brak gramatury w pobliżu". Mierzymy do
# BLIŻSZEGO z dwóch punktów kafelka (cena albo nazwa produktu), bo
# gramatura należy do opisu, nie do ceny.
MAX_SPEC_DISTANCE_RATIO = 0.22


def _normalise_spec(amount: float, unit: str) -> tuple[str, float]:
    unit = unit.lower().rstrip(".")
    if unit == "kg":
        return ("g", amount * 1000)
    if unit == "l":
        return ("ml", amount * 1000)
    if unit == "szt":
        return ("szt", amount)
    return (unit, amount)


def _find_specs(tokens: list[Token], page_width: int) -> list[tuple[Token, str, float]]:
    """Tokeny z wielkością opakowania, znormalizowane do (jednostka, ilość)."""
    specs: list[tuple[Token, str, float]] = []
    max_gap = page_width * 0.03

    for i, t in enumerate(tokens):
        m = SPEC_ONE_TOKEN.match(t.text)
        if m:
            unit, amount = _normalise_spec(float(m.group(1).replace(",", ".")), m.group(2))
            specs.append((t, unit, amount))
            continue

        m = SPEC_GRAMS_AS_NINE.match(t.text)
        if m and int(m.group(1)) % 10 == 0 and 20 <= int(m.group(1)) <= 5000:
            specs.append((t, "g", float(m.group(1))))
            continue

        if not SPEC_NUMBER.match(t.text):
            continue
        for other in tokens:
            if other is t or not SPEC_UNIT.match(other.text):
                continue
            if other.left < t.left or other.left - (t.left + t.width) > max_gap:
                continue
            if abs(other.top - t.top) > t.height:
                continue
            unit, amount = _normalise_spec(float(t.text.replace(",", ".")), other.text)
            specs.append((t, unit, amount))
            break

    return specs


def unit_price_scale(price_token: Token, tokens: list[Token],
                     page_width: int) -> str | None:
    """Skala ceny jednostkowej dopisanej przy kwocie ("kg", "l", "szt",
    "100") albo None, gdy to zwykła cena opakowania.

    Wcześniej ta funkcja zwracała tylko True/False i taka cena szła do
    kosza. To poprawnie chroniło przed absurdami w rodzaju "masło 54,90
    zł" (cena za kilogram wzięta za cenę kostki), ale przy okazji
    wyrzucało produkty sprzedawane NA WAGĘ, gdzie cena za kilogram jest
    jedyną, jaka na gazetce istnieje (papryka 5,99/kg, filet z kurczaka
    14,99/kg). Teraz rozróżniamy te dwa przypadki: patrz
    extract_candidates."""
    m = UNIT_PRICE_INLINE.search(price_token.text)
    if m:
        return m.group(2).lower()

    max_gap = page_width * 0.05
    for t in tokens:
        m = UNIT_PRICE_SUFFIX.match(t.text)
        if t is price_token or not m:
            continue
        if t.left < price_token.left:
            continue
        if t.left - (price_token.left + price_token.width) > max_gap:
            continue
        if abs(t.top - price_token.top) > price_token.height:
            continue
        return m.group(2).lower()
    return None


def _is_unit_price(price_token: Token, tokens: list[Token], page_width: int) -> bool:
    return unit_price_scale(price_token, tokens, page_width) is not None


# Cena "za kilogram" produktu sprzedawanego na wagę to w praktyce cena za
# gram — kupujesz dokładnie tyle, ile trzeba. Modelujemy to jako
# opakowanie o wielkości 1 g/1 ml, dzięki czemu reszta apki (koszt =
# liczba opakowań * cena opakowania) liczy taki składnik proporcjonalnie,
# bez żadnego wyjątku w kodzie: 300 g piersi z kurczaka to 300 "opakowań"
# po 1 g. Dla produktów pakowanych zasada pozostaje bez zmian — 30 g
# masła oznacza całą kostkę.
LOOSE_SCALE_UNIT = {"kg": "g", "l": "ml"}


# ---------------------------------------------------------------------------
# Kontekst kafelka: warunki promocji i okres obowiązywania
# ---------------------------------------------------------------------------

# Promocja warunkowa ("PRZY ZAKUPIE 5 ... KAŻDA Z 5 SZTUK 1,99") to NIE
# jest cena jednej sztuki — żeby ją dostać, trzeba wyjść ze sklepu z
# pięcioma kostkami masła. Zapisanie 1,99 jako ceny kostki byłoby po
# prostu nieprawdą. Traktujemy taką ofertę jak WIĘKSZE OPAKOWANIE
# (5 x 200 g za 9,95 zł) i zapisujemy obok zwykłej kostki: apka sama
# wybierze tańszy wariant dla konkretnego przepisu, a przy 30 g masła
# uczciwie zostanie przy pojedynczej kostce.
BUNDLE_X_PLUS_Y = re.compile(r'\b(\d)\s*\+\s*(\d)\s*gratis\b')
BUNDLE_PRZY_ZAKUPIE = re.compile(r'\bprzy\s+zakupi[eu]\s+(\d)\b')
BUNDLE_KAZDA_Z = re.compile(r'\bkazd[aey]\s*z\s*(\d)\s*szt')
# "OFERTA OD 10.09 DO 12.09" — gazetka trwa tydzień, ale pojedyncza
# promocja bywa krótsza. Data z kafelka jest dokładniejsza niż data
# całej gazetki, więc cena wygasa wtedy, kiedy naprawdę wygasa.
OFFER_PERIOD = re.compile(
    r'\bod\s+(\d{1,2})[.,](\d{1,2})\s+do\s+(\d{1,2})[.,](\d{1,2})\b')
# Promocje "z kartą lub apką" wymagają karty Moja Biedronka — cena bez
# niej jest inna, więc apka musi to napisać wprost.
# Odstęp jest opcjonalny: znaczek "Z KARTĄ LUB APKĄ" jest ciasno złożony
# i wraca z OCR jako jedno słowo "ZKARTĄ".
LOYALTY = re.compile(r'\bz\s*kart|moja\s*biedronka|\bz\s*apk')

# Dwa promienie, bo dwa różne ryzyka. Warunek promocji ("przy zakupie
# 5") ZMIENIA CENĘ, więc wolno go czytać tylko z bezpośredniego
# otoczenia kwoty — wciągnięty z sąsiedniego kafelka zepsułby ją.
# Data obowiązywania zmienia tylko okres ważności i stoi w rogu
# kafelka, daleko od ceny, więc tu opłaca się szukać szerzej.
TILE_RADIUS_RATIO = 0.16
PERIOD_RADIUS_RATIO = 0.28


def tile_text(price_token: Token, tokens: list[Token], page_width: int,
              radius_ratio: float = TILE_RADIUS_RATIO) -> str:
    """Tekst kafelka wokół ceny, złożony w kolejności czytania i
    znormalizowany (bez polskich znaków, małymi literami).

    Warunki promocji są rozsypane po kilku tokenach ("PRZY", "ZAKUPIE",
    "5"), więc regexy stosujemy do sklejonego tekstu, a nie do
    pojedynczych słów. Kolejność musi być czytelniczo poprawna: przy
    naiwnym sortowaniu po (wysokość // stała, lewa krawędź) wiersze
    kafelka przeplatały się ze sobą ("przy 66% kazda taniej zakupie")
    i żaden warunek się nie dopasowywał — dlatego wiersze wyznaczamy
    przez grupowanie, a nie przez dzielenie współrzędnej."""
    radius = page_width * radius_ratio
    near = [t for t in tokens if price_token.distance_to(t) <= radius]
    if not near:
        return ""

    heights = sorted(t.height for t in near)
    line_gap = max(1, heights[len(heights) // 2])

    near.sort(key=lambda t: t.cy)
    rows: list[list[Token]] = [[near[0]]]
    for t in near[1:]:
        if t.cy - rows[-1][-1].cy > line_gap:
            rows.append([])
        rows[-1].append(t)

    words = []
    for row in rows:
        row.sort(key=lambda t: t.left)
        words.extend(t.text for t in row)
    return fold(" ".join(words), ocr_digits=False)


def find_bundle(text: str) -> dict | None:
    """Warunek "kup N sztuk" wyczytany z kafelka: ile sztuk trzeba wziąć
    (`total_units`) i za ile z nich się płaci (`paid_units`)."""
    m = BUNDLE_X_PLUS_Y.search(text)
    if m:
        paid, free = int(m.group(1)), int(m.group(2))
        if 1 <= paid <= 5 and 1 <= free <= 3:
            return {"paid_units": paid, "total_units": paid + free}

    for pattern in (BUNDLE_PRZY_ZAKUPIE, BUNDLE_KAZDA_Z):
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 6:
                return {"paid_units": n, "total_units": n}
    return None


def find_offer_period(text: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """((dzień, miesiąc) od, (dzień, miesiąc) do) z napisu na kafelku."""
    m = OFFER_PERIOD.search(text)
    if not m:
        return None
    d1, m1, d2, m2 = (int(g) for g in m.groups())
    if not (1 <= d1 <= 31 and 1 <= m1 <= 12 and 1 <= d2 <= 31 and 1 <= m2 <= 12):
        return None
    return ((d1, m1), (d2, m2))


def extract_candidates(tokens: list[Token], page_width: int, debug: bool = False) -> list[dict]:
    """Oferty wyciągnięte ze strony gazetki: każdą cenę wiążemy z
    NAJBLIŻSZĄ przestrzennie nazwą składnika, gramaturą i tekstem
    kafelka (warunki promocji, daty).

    Zwraca listę słowników:
      ingredient_name, package_price, unit, unit_amount, unit_price,
      bundle_units (ile sztuk trzeba kupić; 1 = zwykłe opakowanie),
      single_price (cena jednej sztuki w ofercie warunkowej),
      loyalty (czy wymaga karty Moja Biedronka),
      sold_loose (produkt na wagę — koszt liczy się proporcjonalnie),
      valid_from / valid_to jako (dzień, miesiąc) albo None,
      _name_token (do odsiania duplikatów, patrz niżej).
    """
    names = [(t, ing) for t in tokens if (ing := fuzzy_ingredient(t.text))]
    if not names:
        return []

    specs = _find_specs(tokens, page_width)
    max_name_distance = page_width * MAX_NAME_DISTANCE_RATIO
    max_spec_distance = page_width * MAX_SPEC_DISTANCE_RATIO

    candidates: list[dict] = []
    for price_token, amount_pln in find_prices(tokens, page_width):
        name_token, ingredient_name, name_distance = None, None, None
        for t, ing in names:
            d = price_token.distance_to(t)
            if name_distance is None or d < name_distance:
                name_token, ingredient_name, name_distance = t, ing, d
        if name_distance is None or name_distance > max_name_distance:
            continue

        base_unit = unit_for(ingredient_name)
        best_spec, spec_distance = None, None
        for t, unit, spec_amount in specs:
            if unit != base_unit:
                continue
            d = min(price_token.distance_to(t), name_token.distance_to(t))
            if spec_distance is None or d < spec_distance:
                best_spec, spec_distance = (unit, spec_amount), d
        has_spec = best_spec is not None and spec_distance <= max_spec_distance

        # Cena z dopiskiem "/kg" obok ceny opakowania to drobny druk, nie
        # kwota do zapłaty — ale przy produkcie NA WAGĘ jest jedyną ceną,
        # jaka na gazetce w ogóle istnieje. Rozróżniamy je po tym, czy
        # obok jest gramatura opakowania: jest — to produkt pakowany i
        # cena za kilogram jest tylko informacją; nie ma — to waga.
        scale = unit_price_scale(price_token, tokens, page_width)
        sold_loose = False
        if scale is not None:
            if has_spec or LOOSE_SCALE_UNIT.get(scale) != base_unit:
                if debug:
                    print(f"      [gazetka] pomijam {amount_pln} zł/{scale} przy "
                          f"'{name_token.text}' — to cena jednostkowa, nie cena opakowania")
                continue
            sold_loose = True
            unit, unit_amount = base_unit, 1.0
            amount_pln = amount_pln / 1000.0
        elif has_spec:
            unit, unit_amount = best_spec
        else:
            if debug:
                print(f"      [gazetka] {amount_pln} zł przy '{name_token.text}' "
                      f"({ingredient_name}) — brak gramatury w pobliżu, pomijam")
            continue

        text = tile_text(price_token, tokens, page_width)
        bundle = None if sold_loose else find_bundle(text)
        single_price = amount_pln
        if bundle:
            # Cena na kafelku dotyczy JEDNEJ sztuki z zestawu; realna
            # kwota do zapłaty to cena * liczba płatnych sztuk, a
            # dostajesz total_units sztuk.
            amount_pln = round(single_price * bundle["paid_units"], 2)
            unit_amount = unit_amount * bundle["total_units"]

        unit_price = unit_price_of(ingredient_name, amount_pln, unit, unit_amount)
        if unit_price is None:
            continue

        if not is_plausible(ingredient_name, unit_price):
            if debug:
                print(f"      [gazetka] odrzucam {ingredient_name}: {amount_pln} zł "
                      f"za {unit_amount:g}{unit} = {round(unit_price, 3)} zł/j. "
                      f"(poza zakresem wiarygodności)")
            continue

        period = find_offer_period(
            tile_text(price_token, tokens, page_width, PERIOD_RADIUS_RATIO))

        if debug:
            extra = []
            if bundle:
                extra.append(f"przy zakupie {bundle['total_units']} szt.")
            if sold_loose:
                extra.append("na wagę")
            if period:
                extra.append(f"oferta {period[0][0]}.{period[0][1]}-{period[1][0]}.{period[1][1]}")
            print(f"      [gazetka] {ingredient_name}: {amount_pln} zł za {unit_amount:g}{unit} "
                  f"(nazwa '{name_token.text}' w {name_distance:.0f}px"
                  + (f", {', '.join(extra)}" if extra else "") + ")")

        candidates.append({
            "ingredient_name": ingredient_name,
            "package_price": amount_pln,
            "unit": unit,
            "unit_amount": unit_amount,
            "unit_price": unit_price,
            "bundle_units": bundle["total_units"] if bundle else 1,
            "single_price": single_price,
            "loyalty": bool(LOYALTY.search(text)),
            "sold_loose": sold_loose,
            "valid_from": period[0] if period else None,
            "valid_to": period[1] if period else None,
            "_name_token": id(name_token),
        })

    return _drop_redundant_loose(candidates)


def _drop_redundant_loose(candidates: list[dict]) -> list[dict]:
    """Gdy przy tej samej nazwie odczytaliśmy i cenę opakowania, i cenę
    za kilogram, cena za kilogram jest tylko drobnym drukiem — produkt
    jest pakowany, więc kupuje się całe opakowanie. Zostawiamy ją tylko
    tam, gdzie nic innego przy tej nazwie nie było."""
    packaged = {c["_name_token"] for c in candidates if not c["sold_loose"]}
    return [c for c in candidates
            if not (c["sold_loose"] and c["_name_token"] in packaged)]
