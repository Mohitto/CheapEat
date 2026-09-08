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

# Domyślne wartości odżywcze dla kategorii, których może jeszcze nie być
# w tabeli `ingredients` (scraper tworzy brakujący wiersz przy pierwszym
# trafieniu) — przybliżone, wystarczające do wyświetlenia w apce.
INGREDIENT_DEFAULTS: dict[str, dict] = {
    "mięso mielone": {"protein_per_100g": 17.0, "kcal_per_100g": 254},
    "jajka": {"protein_per_100g": 12.5, "kcal_per_100g": 143},
}

# Rozsądny przedział ceny za 100g/100ml dla każdej kategorii. OCR i
# dopasowanie kontekstu regularnie się mylą (zgubiona cyfra, zły
# przecinek, cena sąsiedniego produktu w oknie kontekstu) — dopasowanie
# spoza tego zakresu jest ODRZUCANE. Lepiej brakująca cena niż pewna
# siebie zła cena (patrz historia tej sesji: dokładnie ten błąd
# naprawialiśmy dla wzoru matematycznego, teraz naprawiamy dla OCR).
PLAUSIBLE_RANGE_PER_100: dict[str, tuple[float, float]] = {
    "mąka pszenna": (0.2, 1.0),
    "cukier": (0.2, 1.0),
    "masło": (2.0, 8.0),
    "ryż": (0.3, 2.0),
    "kurczak pierś": (1.2, 4.0),
    "mięso mielone": (1.0, 3.5),
    "cebula": (0.1, 0.8),
    "pomidor": (0.3, 2.5),
    "ser żółty": (1.0, 6.0),
    "olej rzepakowy": (0.5, 2.5),
    "sól": (0.1, 0.6),
    "mleko": (0.2, 1.0),
    "jajka": (0.8, 4.0),
}

# Średnia waga sztuki [g] dla produktów liczonych na sztuki, nie na wagę
# (np. "10 szt jajek za X zł") — potrzebne żeby przeliczyć na cenę za
# 100g. Przybliżenie (prawdziwa waga zależy od klasy L/M/S), ale
# wystarczające przy filtrze prawdopodobieństwa powyżej.
AVERAGE_UNIT_WEIGHT_G: dict[str, float] = {
    "jajka": 60.0,
}


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
        for kw in keywords:
            pos = text_lower.rfind(kw)
            if pos > best_pos:
                best_pos = pos
                best_name = ingredient_name
    return best_name


def is_plausible(ingredient_name: str, price_per_100: float) -> bool:
    lo, hi = PLAUSIBLE_RANGE_PER_100.get(ingredient_name, (0.0, 0.0))
    return lo <= price_per_100 <= hi
