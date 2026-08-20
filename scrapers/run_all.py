"""Uruchamia wszystkie scrapery sekwencyjnie. Używany przez GitHub Actions."""
import sys
import json
from datetime import datetime

from biedronka.scraper import BiedronkaScraper
from lidl.scraper import LidlScraper
# from aldi.scraper import AldiScraper      # odkomentuj gdy gotowy

SCRAPERS = [
    BiedronkaScraper,
    LidlScraper,
]


def main():
    results = {}
    errors = {}

    for ScraperClass in SCRAPERS:
        name = ScraperClass.store_name
        print(f"\n{'='*50}")
        print(f"Scraper: {name}")
        print(f"{'='*50}")
        try:
            result = ScraperClass().scrape()
            results[name] = result
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            errors[name] = str(e)

    print("\n" + "="*50)
    print("PODSUMOWANIE")
    print(json.dumps({"results": results, "errors": errors}, indent=2, ensure_ascii=False))

    if errors:
        print(f"\n[WARN] {len(errors)} scraper(y) zakończyły się błędem")
        sys.exit(1)

    print(f"\n[OK] Wszystkie scrapery zakończyły się sukcesem: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
