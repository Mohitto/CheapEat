# CheapEat Scrapers

Skrypty Python do zbierania danych o promocjach ze sklepów.

## Struktura

```
scrapers/
├── base_scraper.py       # Wspólna logika (Supabase client, upsert)
├── run_all.py            # Entry point dla GitHub Actions
├── seed_dev_data.py      # Dane testowe (NIE scraping) — pełny przepływ do testów
├── requirements.txt
├── .env.example
├── biedronka/
│   ├── scraper.py          # Scraper Biedronki (API + HTML fallback, endpoint niezweryfikowany)
│   └── __init__.py
└── lidl/
    ├── scraper.py          # Scraper Lidla (best-effort szkielet, endpoint niezweryfikowany)
    └── __init__.py
```

## Uruchomienie lokalne

```bash
cd scrapers
cp .env.example .env
# Uzupełnij .env: SUPABASE_URL i SUPABASE_SERVICE_KEY (service role!)
pip install -r requirements.txt

# Jeden sklep
python -m biedronka.scraper

# Wszystkie
python run_all.py
```

## Dane testowe (bez scrapingu)

Zanim scrapery Biedronki/Lidla i scraper przepisów będą gotowe do produkcji,
`seed_dev_data.py` wstawia ręcznie kilkanaście składników, produkty sklepowe
z cenami "gazetkowymi" i 3 przepisy testowe (`[TEST] ...`) — wystarczająco,
żeby w apce zobaczyć realnie liczący się koszt zakupów dla przepisu:

```bash
python seed_dev_data.py
```

Skrypt jest idempotentny (bezpiecznie odpalić kilka razy). Nazwy kolumn są
wywnioskowane z kodu aplikacji, nie zweryfikowane na żywej bazie — jeśli
insert zwróci błąd wskazujący konkretną kolumnę, popraw ją w skrypcie.

## GitHub Actions

Cron scrapera odpala się automatycznie **w środę o 7:00 UTC** (Biedronka zmienia gazetkę środę).
Runner GitHub Actions ma pełny dostęp do internetu (w przeciwieństwie do sandboxa
Claude Code) — to jedyne miejsce, gdzie scrapery/seed script realnie się wykonają.

### Wymagane GitHub Secrets

Dodaj w: `Settings → Secrets and variables → Actions → New repository secret`

| Secret | Wartość |
|--------|----------|
| `SUPABASE_URL` | URL projektu Supabase (`https://<ref>.supabase.co`) |
| `SUPABASE_SERVICE_KEY` | **secret** key projektu (nowy format: `sb_secret_...`; nie `sb_publishable_...`/anon!) |

Te same dwa sekrety obsługują oba workflow — `Scrape Flyers` i `Seed Dev Data`.

### Ręczne odpalenie

- Scraper: `Actions → Scrape Flyers → Run workflow`
- Dane testowe (patrz sekcja wyżej): `Actions → Seed Dev Data → Run workflow`

## Dodawanie nowego sklepu

1. Utwórz katalog `scrapers/<sklep>/`
2. Napisz `scraper.py` dziedzicząc z `BaseScraper`
3. Ustaw `store_name` i `store_website`
4. Zaimplementuj `scrape()`
5. Dodaj import + wpis w `SCRAPERS` w `run_all.py`
