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
└── biedronka/
    ├── scraper.py          # Scraper Biedronki (API + HTML fallback, endpoint niezweryfikowany)
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

Cron odpala się automatycznie **w środę o 7:00 UTC** (Biedronka zmienia gazetkę środę).

### Wymagane GitHub Secrets

Dodaj w: `Settings → Secrets and variables → Actions`

| Secret | Wartość |
|--------|----------|
| `SUPABASE_URL` | URL projektu Supabase |
| `SUPABASE_SERVICE_KEY` | Service role key (nie anon!) |

### Ręczne odpalenie

`Actions → Scrape Flyers → Run workflow`

## Dodawanie nowego sklepu

1. Utwórz katalog `scrapers/lidl/`
2. Napisz `scraper.py` dziedzicząc z `BaseScraper`
3. Ustaw `store_name` i `store_website`
4. Zaimplementuj `scrape()`
5. Odkomentuj import w `run_all.py`
