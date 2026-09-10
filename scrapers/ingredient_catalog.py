"""
ingredient_catalog.py — wspólny katalog kategorii składników używany przez
WSZYSTKIE scrapery (Biedronka, Lidl, przyszłe sklepy), żeby klasyfikowały
identycznie i były łatwe do rozszerzania w jednym miejscu.

Kluczowa zasada: dopasowanie jest markowo-agnostyczne. Sprawdzamy tylko
czy TYP produktu (podciąg tekstu) występuje gdziekolwiek w nazwie/opisie —
marka ("Mała Kurka", "Zielone Pastwisko"), klasa (L/M/S) czy dokładna
gramatura nie mają znaczenia. Każde jajko, niezależnie od marki i klasy,
trafia w kategorię "jajka".
"""
import re

# Nazwa naszego składnika (musi istnieć w tabeli `ingredients` — patrz
# seed_dev_data.py; scrapery dotwarzają brakujące przez get_or_create)
# -> słowa kluczowe szukane w tekście produktu.
INGREDIENT_KEYWORDS: dict[str, list[str]] = {
    "mąka pszenna": ["mąka pszenna", "mąka"],
    "cukier": ["cukier"],
    "masło": ["masło"],
    "ryż": ["ryż"],
    "kurczak pierś": ["pierś z kurczaka", "filet z kurczaka", "kurczak"],
    "mięso mielone": ["mięso mielone", "mielone wieprzowo", "mielone wołowo",
                       "mielona wieprzowo", "mielona wołowo", "mięso mielon"],
    "cebula": ["cebula"],
    "pomidor": ["pomidor"],
    "ser żółty": ["ser żółty", "ser gouda", "ser edamski", "ser salami"],
    "olej rzepakowy": ["olej rzepakowy", "olej"],
    "sól": ["sól"],
    "mleko": ["mleko"],
    "jajka": ["jajka", "jajko", "jaja", "jajek", "jajami"],
}

# Skanowanie 1000+ realnych produktów sklepowych (zakupy.biedronka.pl,
# potwierdzone na żywo) ujawniło fałszywe trafienia, których krótkie
# słowa kluczowe powyżej nie odróżniają od prawdziwego produktu — np.
# "Vifon Zupa błyskawiczna o smaku kurczaka" (zupa w proszku, nie pierś
# z kurczaka), "Go Vege Masło orzechowe" (masło orzechowe, nie masło
# mleczne), "Lisner Jajko sałatka warzywna z jajkiem" (sałatka, nie
# jajka), "Profi Pasztet z pomidorami" (pasztet, nie pomidor). Zakres
# is_plausible łapie część takich przypadków (cena dopasowanego
# produktu wypada absurdalnie wysoko/nisko dla kategorii), ale nie
# wszystkie — cena pasztetu czy sałatki jajecznej bywa przypadkowo w
# granicach prawdopodobieństwa dla pomidora/jajek. Jeśli którekolwiek z
# tych słów występuje w tekście, kategoria jest pomijana — lepiej
# brakująca cena niż cena zupełnie innego produktu.
INGREDIENT_EXCLUDE_KEYWORDS: dict[str, list[str]] = {
    "kurczak pierś": ["zupa", "burger", "pizza", "tortilla", "kabanos",
                       "parówk", "kiełbas", "przekąska", "sałatka", "gyros"],
    "masło": ["orzechowe", "orzechowym"],
    "jajka": ["sałatka", "sałatką"],
    "pomidor": ["pasztet", "sos", "koncentrat", "pesto", "sok", "pulpa"],
    "ryż": ["chleb", "wafle", "wafel"],
}

# Domyślne wartości odżywcze dla kategorii, których może jeszcze nie być
# w tabeli `ingredients` (scraper tworzy brakujący wiersz przy pierwszym
# trafieniu) — przybliżone, wystarczające do wyświetlenia w apce.
INGREDIENT_DEFAULTS: dict[str, dict] = {
    "mięso mielone": {"protein_per_100g": 17.0, "kcal_per_100g": 254},
    "jajka": {"protein_per_100g": 12.5, "kcal_per_100g": 143},
}

# Jednostka, w której NAPRAWDĘ kupuje się dany składnik. Domyślnie waga
# ("g") lub objętość ("ml"), ale część produktów sprzedaje się wyłącznie
# na sztuki — jajek nikt nie kupuje na gramy, więc przeliczanie ich przez
# zmyśloną średnią wagę sztuki (i pokazywanie "120 g jajek") było błędem.
# Sklep sam podaje to wprost, np. "10szt. - 1,40 zł / szt".
INGREDIENT_UNIT: dict[str, str] = {
    "jajka": "szt",
    "mleko": "ml",
    # Olej sprzedaje się w litrach, nie na wagę — przy jednostce "g"
    # gazetkowe "1 l" było odrzucane jako niezgodna jednostka i realna
    # promocja (4,49 zł za litr) przepadała.
    "olej rzepakowy": "ml",
}


def unit_for(ingredient_name: str) -> str:
    """Jednostka bazowa składnika: 'szt', 'ml' albo (domyślnie) 'g'."""
    return INGREDIENT_UNIT.get(ingredient_name, "g")

# Rozsądny przedział ceny jednostkowej dla każdej kategorii: za 100g/100ml
# dla składników ważonych, a za 1 SZTUKĘ dla tych z INGREDIENT_UNIT == "szt"
# (jajka). OCR i dopasowanie kontekstu regularnie się mylą (zgubiona cyfra,
# zły przecinek, cena sąsiedniego produktu w oknie kontekstu) — dopasowanie
# spoza tego zakresu jest ODRZUCANE. Lepiej brakująca cena niż pewna
# siebie zła cena (patrz historia tej sesji: dokładnie ten błąd
# naprawialiśmy dla wzoru matematycznego, teraz naprawiamy dla OCR).
#
# Dolne granice są celowo NISKIE. Ustawione "na oko wokół ceny
# regularnej" odcinały prawdziwe promocje: masło Ekstra 200 g po 1,99 zł
# (przy zakupie 5) to 0,995 zł/100 g, czyli tuż pod dawnym progiem 1,0 —
# realna promocja z pierwszej strony gazetki wypadała jako "niewiarygodna".
# Gazetkowe -50%/-66% to norma, więc próg musi ją przepuszczać. Zadaniem
# dolnej granicy jest łapanie zgubionej cyfry (1,99 odczytane jako 0,99
# przy kilogramie), a nie ocenianie, czy promocja jest "za dobra".
PLAUSIBLE_UNIT_PRICE: dict[str, tuple[float, float]] = {
    "mąka pszenna": (0.05, 1.0),
    "cukier": (0.05, 1.0),
    "masło": (0.5, 8.0),
    "ryż": (0.15, 2.0),
    "kurczak pierś": (0.6, 4.0),
    "mięso mielone": (0.5, 3.5),
    "cebula": (0.05, 0.8),
    "pomidor": (0.15, 2.5),
    "ser żółty": (0.5, 6.0),
    "olej rzepakowy": (0.3, 2.5),
    "sól": (0.05, 0.6),
    "mleko": (0.12, 1.0),
    # za 1 sztukę, nie za 100 g — realne ceny w sklepie to 1,35-1,60 zł/szt,
    # w promocji potrafi zejść poniżej złotówki.
    "jajka": (0.2, 3.0),
}


# Słowa, które fuzzy-dopasowanie brałoby za nasz składnik, a są zupełnie
# innym produktem. Polskiej morfologii nie da się tu rozstrzygnąć regułą:
# "cukier" + "ki" to cukierki (słodycz), a nie cukier; "mielonka" (konserwa)
# jest o jedną literę od "mielone". Lista jest z obserwacji, jak
# INGREDIENT_EXCLUDE_KEYWORDS — rozszerzana, gdy coś realnie przecieknie.
FUZZY_BLOCKED_WORDS = {
    "cukierki", "cukierek", "cukierka", "cukierkow", "cukiereczki",
    "mielonka", "mielonki", "serek", "serki", "serka",
    "jajecznica", "maslanka", "maslanki",
}

_DIACRITICS = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
    "ó": "o", "ś": "s", "ź": "z", "ż": "z",
})
# OCR na stylizowanych, dużych napisach gazetki regularnie myli znaki o
# podobnym kształcie ("masło" -> "masto"/"masio", "ryż" -> "ryz"/"rvz").
_OCR_CONFUSIONS = str.maketrans({"1": "l", "0": "o", "5": "s", "8": "b", "|": "l", "!": "l"})


# Wielkie "I" i małe "l" to w bezszeryfowym foncie ta sama kreska —
# rozstrzygamy to PRZED zmianą wielkości liter, bo po .lower() informacja
# o wielkości znika i "mIeko" (czyli "mleko") remisuje z "mięso".
_CASE_SENSITIVE_CONFUSIONS = str.maketrans({"I": "l"})


def fold(text: str, ocr_digits: bool = True) -> str:
    """Postać porównawcza odporna na polskie znaki i typowe pomyłki OCR.

    `ocr_digits` mapuje cyfry na podobne litery ("1"->"l", "0"->"o") i jest
    tym, czego potrzeba przy porównywaniu NAZW. Przy czytaniu tekstu, w
    którym liczby coś znaczą — "PRZY ZAKUPIE 5", "OFERTA OD 10.09" —
    trzeba go wyłączyć, bo inaczej warunek promocji zamienia się w
    "przy zakuple s", a data w "lo.o9", i żaden wzorzec ich nie widzi."""
    folded = text.translate(_CASE_SENSITIVE_CONFUSIONS).lower().translate(_DIACRITICS)
    return folded.translate(_OCR_CONFUSIONS) if ocr_digits else folded


def fuzzy_ingredient(word: str, min_ratio: float = 0.80) -> str | None:
    """Kategoria składnika dla POJEDYNCZEGO słowa z OCR, tolerancyjnie na
    przekręcone litery. Używane przy gazetce, gdzie tekst jest odczytany
    z obrazka — "masto 82%" ma trafić w "masło". Krótkie słowa (<4 znaki)
    porównujemy tylko dokładnie, bo przy nich każda pomyłka to inne słowo."""
    from difflib import SequenceMatcher

    cleaned = fold(word.strip(" ,.:;()[]%*"))
    if len(cleaned) < 3 or cleaned in FUZZY_BLOCKED_WORDS:
        return None

    best_name, best_score = None, 0.0
    for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
        for kw in keywords:
            # Słowa kluczowe wielowyrazowe ("mięso mielone") nie wystąpią
            # jako pojedynczy token — porównujemy z ich członami.
            for part in fold(kw).split():
                if len(part) < 4:
                    if cleaned == part:
                        return ingredient_name
                    continue

                if cleaned == part:
                    return ingredient_name

                # Odmiana ("kurczaka", "pomidory") to najwyżej kilka liter
                # dosklejonych na końcu; bez limitu długości "makaron"
                # trafiałby w "mąka".
                if cleaned.startswith(part) and len(cleaned) - len(part) <= 2:
                    return ingredient_name

                score = SequenceMatcher(None, cleaned, part).ratio()
                # Bierzemy NAJLEPSZE dopasowanie, nie pierwsze powyżej progu:
                # "mieko" (OCR z "mleko") pasuje i do "mleko", i do "mięso",
                # a kolejność w słowniku nie powinna o tym decydować.
                if score >= min_ratio and score > best_score:
                    best_name, best_score = ingredient_name, score

    return best_name


def match_ingredient(text: str) -> str | None:
    """Zwraca nazwę kategorii dopasowaną do tekstu (dopasowanie
    podciągu, bez rozróżniania wielkości liter) albo None.

    Gdy `text` to okno kontekstu tuż przed ceną na gęstej stronie z wieloma
    produktami, więcej niż jedna kategoria może mieć tam jakieś trafienie
    (np. nazwa poprzedniego produktu na tej samej stronie). Bierzemy
    kategorię, której NAJBLIŻSZE (najdalej wysunięte w prawo, czyli
    najbliżej ceny) wystąpienie słowa kluczowego jest najbliżej końca
    tekstu — nie po prostu pierwszą pasującą wg kolejności w słowniku,
    bo to prowadziło do przypisywania ceny zupełnie innego produktu do
    przypadkowej, wcześniejszej kategorii w oknie."""
    text_lower = text.lower()
    best_name = None
    best_pos = -1
    for ingredient_name, keywords in INGREDIENT_KEYWORDS.items():
        if any(x in text_lower for x in INGREDIENT_EXCLUDE_KEYWORDS.get(ingredient_name, ())):
            continue
        for kw in keywords:
            pos = text_lower.rfind(kw)
            if pos > best_pos:
                best_pos = pos
                best_name = ingredient_name
    return best_name


def is_plausible(ingredient_name: str, unit_price: float) -> bool:
    """`unit_price` w jednostce bazowej składnika: zł/100g, zł/100ml
    albo zł/szt (patrz INGREDIENT_UNIT i PLAUSIBLE_UNIT_PRICE)."""
    lo, hi = PLAUSIBLE_UNIT_PRICE.get(ingredient_name, (0.0, 0.0))
    return lo <= unit_price <= hi


def unit_price_of(ingredient_name: str, package_price: float,
                  unit: str, unit_amount: float) -> float | None:
    """Cena jednostkowa opakowania w jednostce bazowej składnika —
    do porównywania opakowań różnej wielkości i do is_plausible.
    Zwraca None, gdy jednostka opakowania nie pasuje do składnika
    (np. mięso na sztuki), bo wtedy nie ma bezpiecznego przelicznika."""
    if unit_amount <= 0 or unit != unit_for(ingredient_name):
        return None
    if unit == "szt":
        return package_price / unit_amount          # zł za sztukę
    return package_price / (unit_amount / 100.0)    # zł za 100 g/ml


# Gramatura/objętość opakowania NIE jest zwykle ujawniana jako osobne pole
# strukturalne (ani w SSR-JSON Lidla, ani w data-product-gtm Biedronki) —
# ale polskie nazwy produktów spożywczych zwyczajowo zawierają ją wprost
# w tytule (np. "Cukier biały 1 kg", "Mleko 3,2% 1l", "Jajka 10 szt"). Bez
# tego nie da się BEZPIECZNIE przeliczyć ceny opakowania na cenę za
# 100g/ml — zgadywanie stałej gramatury odtworzyłoby dokładnie ten sam
# błąd (absurdalne ceny), naprawiony wcześniej w tej sesji. Więc: znajdź
# gramaturę/ilość w tytule albo pomiń produkt, nigdy nie zgaduj. Współdzielone
# przez wszystkie scrapery sklepowe (Lidl, Biedronka-sklep, przyszłe).
GRAMMAGE_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b', re.IGNORECASE)
COUNT_PATTERN = re.compile(r'(\d{1,2})\s*szt\b', re.IGNORECASE)


def parse_package_spec(text: str, ingredient_name: str) -> tuple[str, float] | None:
    """Zwraca ("szt"|"g"|"ml", ilość) opakowania wyczytaną z tekstu
    (zwykle nazwy produktu), albo None gdy nie da się jej ustalić.

    Dla składników sprzedawanych na sztuki (INGREDIENT_UNIT == "szt")
    liczymy WYŁĄCZNIE sztuki — nie przeliczamy ich na gramy przez średnią
    wagę, bo nikt nie kupuje jajek na wagę, a taka konwersja produkowała
    absurdy w rodzaju "120 g jajek". Dla reszty bierzemy gramaturę; "X szt"
    sprawdzamy pierwsze, bo w dłuższym tekście GRAMMAGE_PATTERN potrafi
    złapać liczbę z tabeli wartości odżywczych zamiast wagi opakowania."""
    if unit_for(ingredient_name) == "szt":
        m = COUNT_PATTERN.search(text)
        return ("szt", float(m.group(1))) if m else None

    m = GRAMMAGE_PATTERN.search(text)
    if m:
        amount = float(m.group(1).replace(",", "."))
        unit = m.group(2).lower()
        if unit == "kg":
            return ("g", amount * 1000)
        if unit == "l":
            return ("ml", amount * 1000)
        return (unit, amount)

    return None
