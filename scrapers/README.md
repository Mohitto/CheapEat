# CheapEat Scrapers

Skrypty Python do zbierania danych o promocjach ze sklepów — cen
regularnych i gazetkowych, wpisywanych do Supabase i stamtąd czytanych
przez apkę (WatermelonDB synchronizuje się z tą samą bazą).

## Struktura

```
scrapers/
├── base_scraper.py        # get_supabase, get_or_create, replace_price — wspólne dla wszystkich scraperów
├── ingredient_catalog.py  # WSPÓLNY dla wszystkich sklepów: kategorie składników, jednostki,
│                          # zakresy wiarygodności ceny, dopasowanie nazw tolerancyjne na OCR
├── flyer_ocr.py           # WSPÓLNY silnik OCR gazetki-jako-obrazka (patrz niżej) — używany
│                          # dziś tylko przez Biedronkę, ale nie jest do niej przywiązany
├── run_all.py             # Entry point dla GitHub Actions — lista SCRAPERS
├── verify_recipe_cost.py  # Podgląd kosztu przepisu bez telefonu (patrz sekcja niżej)
├── diagnose_prices.py     # Zrzut wszystkich cen/mapowań per składnik — do debugowania
├── cleanup_*.py           # Sprzątanie danych złych/przestarzałych (patrz docstringi każdego)
├── seed_dev_data.py       # Dane testowe (NIE scraping) — przepisy [TEST] do weryfikacji
├── probe_*.py             # Jednorazowe sondy diagnostyczne — patrz "Sondy" niżej
├── requirements.txt
├── .env.example
├── biedronka/
│   ├── flyers.py           # Odkrywanie gazetek Biedronki i ich ważności (adapter, patrz niżej)
│   ├── scraper.py           # Scraper gazetki: flyers.py + flyer_ocr.py + zapis do bazy
│   ├── shop_scraper.py       # Scraper cen REGULARNYCH z zakupy.biedronka.pl (bez OCR, JSON w HTML)
│   └── __init__.py
└── lidl/
    ├── scraper.py          # Scraper Lidla — parsuje SSR-JSON osadzony w HTML, bez OCR w ogóle
    └── __init__.py
```

## Dwa rodzaje sklepu, dwa rodzaje scrapera

Zanim dodasz nowy sklep, sprawdź, do której kategorii pasuje — to
decyduje, ile w ogóle trzeba napisać.

### A. Sklep publikuje ceny jako DANE (preferowane, mniej pracy)

Większość sklepów sieciowych ma stronę produktową renderowaną
server-side, która w statycznym HTML osadza pełny JSON produktu (cena,
nazwa, czasem gramatura) — nawet jeśli nie ma żadnego publicznego API.
Tak działa dziś **Lidl** (`lidl/scraper.py`): parsuje
HTML-entity-encoded JSON z kategorii `lidl.pl`, bez OCR, bez zgadywania.

Żeby to sprawdzić dla nowego sklepu:
1. Otwórz stronę kategorii/produktu w przeglądarce, `Ctrl+U` (widok
   źródła, NIE devtools — chodzi o to, co przyszło z serwera).
2. Szukaj `Ctrl+F` po cenie widocznej na stronie (np. `12,99` albo
   `12.99`) — jeśli jest w źródle, produkt jest renderowany server-side.
3. Jeśli tak: napisz scraper analogiczny do `lidl/scraper.py` — żadnego
   OCR, żadnej gazetki, tylko parsowanie tego JSON-a.
4. Jeśli sklep ma osobną gazetkę promocyjną OSOBNO od cen ze sklepu
   (tak jak Biedronka), sprawdź czy TA gazetka też jest danymi, zanim
   założysz, że trzeba OCR-ować obrazki (patrz `probe_biedronka_leaflet_api.py`
   jako przykład takiego sprawdzenia — dla Biedronki wyszło, że
   leaflet-api zwraca WYŁĄCZNIE bitmapy stron, stąd wariant B).

### B. Sklep publikuje gazetkę WYŁĄCZNIE jako obrazek (Biedronka)

Gdy sklep faktycznie oddaje tylko bitmapy stron (sprawdzone, nie
zgadnięte — patrz `probe_biedronka_*.py`), jedyna droga to OCR. Cały
silnik do tego jest w **`flyer_ocr.py`** i nie trzeba go pisać od nowa —
napisz tylko adapter analogiczny do `biedronka/flyers.py` +
`biedronka/scraper.py`, złożony z dwóch części:

1. **Odkrywanie gazetek i ich ważności** (wzór: `biedronka/flyers.py`).
   To jest jedyna część naprawdę specyficzna dla sklepu — adres listy
   gazetek, sposób parsowania daty startu/końca z jego strony, ile
   trwa jedna edycja. Zwraca listę `{path, slug, valid_from, valid_to}`.
2. **Pętla scrapera** (wzór: `biedronka/scraper.py`), która:
   - woła adapter z (1), żeby wiedzieć KTÓRE strony czytać i z jaką
     ważnością cen,
   - dla każdej strony woła `flyer_ocr.ocr_page()` (tani przegląd
     tesseractem — sam sprawdza, czy strona wspomina którykolwiek z
     naszych składników) i `flyer_ocr.ocr_page_precise()` (wolny, ale
     jedyny, który faktycznie widzi ceny — patrz niżej, dlaczego dwa),
   - woła `flyer_ocr.extract_candidates()`, która already umie: wiązać
     cenę z najbliższą nazwą i gramaturą, rozpoznawać oferty warunkowe
     ("przy zakupie 5 sztuk"), produkty na wagę, okres ważności z
     kafelka — bez zmian, bo to wszystko jest generyczne.
   - zapisuje wynik przez `base_scraper.replace_price` i porównuje z
     ceną regularną tego składnika (patrz `cheapest_regular_unit_price`
     w `biedronka/scraper.py`) — promocja poniżej 30% ceny regularnej
     jest odrzucana jako zły odczyt, nie prawdziwa okazja.

**Zanim zaczniesz OCR-ować: zmierz, czy silnik w ogóle widzi ten krój.**
Tesseract nie czyta w ogóle cen z gazetki Biedronki (nie "słabo" —
zero), bo to firmowa, stylizowana czcionka z groszami jak indeks górny,
której model `pol` nigdy nie widział. EasyOCR sobie z nią radzi. Inny
sklep może mieć inny krój, więc ten pomiar (`probe_ocr_engines.py` —
uruchamia kilka silników na tej samej stronie i liczy, ile z
NAPRAWDĘ wydrukowanych cen każdy odczytał) warto powtórzyć zamiast
zakładać z góry, że EasyOCR wystarczy. Pełne uzasadnienie i wyniki
pomiaru są w docstringu `flyer_ocr.py`.

### Wspólne dla obu wariantów

Niezależnie od tego, którą drogą idzie sklep, dopasowanie tekstu do
kategorii składnika (`fuzzy_ingredient`/`match_ingredient`), jednostka
bazowa (`unit_for` — sztuki dla jajek, ml dla mleka i oleju, inaczej
gramy) i kontrola wiarygodności ceny (`is_plausible`,
`PLAUSIBLE_UNIT_PRICE`) są w **`ingredient_catalog.py` i mają zostać
wspólne** — nowy sklep nie dostaje własnej kopii tej logiki, tylko
rozszerza słowniki tam, gdzie realnie brakuje pokrycia (np. nowe
`INGREDIENT_EXCLUDE_KEYWORDS`, gdy fałszywe trafienie jest specyficzne
dla asortymentu tego sklepu).

## Rejestracja nowego sklepu

1. `scrapers/<sklep>/` — zaimplementuj wg wariantu A lub B wyżej.
2. `store_name` musi być unikalny wpis w tabeli `stores` (używany przez
   `get_or_create`).
3. Dodaj import + wpis w `SCRAPERS` w `run_all.py`. Jeśli sklep ma
   OSOBNY scraper na ceny regularne i na gazetkę (jak Biedronka —
   `BiedronkaScraper` + `BiedronkaShopScraper`), oba wpisy dzielą
   `store_name`, ale mają różne klasy — `run_all.py` kluczuje wyniki po
   nazwie klasy, nie po sklepie, więc to bezpieczne.
4. Jeśli wariant B: dodaj przypadki testowe do `test_flyer_ocr.py` na
   PRAWDZIWYCH tokenach z tej gazetki (nie z Biedronki) — inny sklep to
   inny krój, inna forma promocji warunkowych, inne pomyłki OCR.

## Sondy diagnostyczne (`probe_*.py`)

Jednorazowe skrypty, które ODPOWIEDZIAŁY na konkretne pytanie w trakcie
budowy — zostają w repo jako udokumentowany wynik pomiaru i jako wzór,
jak sprawdzić to samo dla kolejnego sklepu:

| Pytanie | Skrypt | Odpowiedź |
|---|---|---|
| Czy Biedronka ma jakiekolwiek strukturalne API cen gazetkowych? | `probe_biedronka_leaflet_api.py` | Nie — same bitmapy stron. |
| Czy zakupy.biedronka.pl ma ceny regularne jako dane? | `probe_biedronka_shop.py`, `probe_biedronka_zakupy.py` | Tak — `data-product-gtm` JSON w kafelku. |
| Jakie ustawienia tesseracta czytają najwięcej? | `probe_ocr_settings.py` | psm 11 + 2x. |
| Czy JAKIKOLWIEK darmowy silnik czyta krój cen Biedronki? | `probe_ocr_engines.py` | Tesseract: nie. EasyOCR: tak. |
| Czy API oddaje gazetkę w lepszej rozdzielczości / czy segmentacja strony gubi ceny? | `probe_leaflet_images.py`, `probe_page_tiles.py` | Nie i nie — to krój czcionki, nie rozdzielczość. |

Uruchamiane przez `.github/workflows/probe-biedronka-network.yml`
(`workflow_dispatch`, z parametrami `slug`/`page` gazetki do zbadania).

## Uruchomienie lokalne

```bash
cd scrapers
cp .env.example .env
# Uzupełnij .env: SUPABASE_URL i SUPABASE_SERVICE_KEY (service role!)
pip install -r requirements.txt

# Jeden sklep
python -m biedronka.scraper
python -m lidl.scraper

# Wszystkie
python run_all.py

# Test silnika OCR gazetki, bez sieci i bez tesseracta/EasyOCR
python test_flyer_ocr.py
```

## Podgląd kosztu przepisu bez telefonu

Apka to czysty React Native CLI (bez Expo) — w środowisku headless (bez
Android SDK/Xcode) nie da się zobaczyć przepisu na żywo. `verify_recipe_cost.py`
liczy koszt DOKŁADNIE tym samym algorytmem co
`src/services/{recipeService,priceService,ingredientService}.ts`, ale
bezpośrednio na Supabase — do zsynchronizowania ręcznie, jeśli TS się
zmieni (patrz docstring skryptu).

```bash
python verify_recipe_cost.py "Naleśniki" "Omlet"
```

## Dane testowe (bez scrapingu)

`seed_dev_data.py` wstawia przepisy testowe (`[TEST] ...`) i ich
składniki — same ceny mają już pochodzić WYŁĄCZNIE ze scraperów, nie z
tego skryptu (patrz historia commitów: zmyślone ceny testowe kiedyś
zostawały w bazie i mieszały się z prawdziwymi).

```bash
python seed_dev_data.py
```

Skrypt jest idempotentny (bezpiecznie odpalić kilka razy).

## GitHub Actions

Runner GitHub Actions ma pełny dostęp do internetu (w przeciwieństwie do
sandboxa Claude Code) — to jedyne miejsce, gdzie scrapery realnie się
wykonują. `Verify Recipe Cost` odpala cały pipeline (sprzątanie → seed →
wszystkie scrapery → policzenie kosztu → zrzut diagnostyczny) i jest
najbliższym odpowiednikiem "zobacz, czy to działa" bez telefonu.

### Wymagane GitHub Secrets

Dodaj w: `Settings → Secrets and variables → Actions → New repository secret`

| Secret | Wartość |
|--------|----------|
| `SUPABASE_URL` | URL projektu Supabase (`https://<ref>.supabase.co`) |
| `SUPABASE_SERVICE_KEY` | **secret** key projektu (nowy format: `sb_secret_...`; nie `sb_publishable_...`/anon!) |
