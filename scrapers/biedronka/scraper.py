"""Scraper gazetki Biedronka.

API Biedronki zwraca JSON z aktualnymi promocjami.
Endpoint: https://www.biedronka.pl/pl/offers-api
"""
import sys
import os
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import BaseScraper


BIEDRONKA_API = "https://www.biedronka.pl/pl/offers-api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CheapEatBot/1.0)",
    "Accept": "application/json",
    "Accept-Language": "pl-PL,pl;q=0.9",
}


class BiedronkaScraper(BaseScraper):
    store_name = "Biedronka"
    store_website = "https://www.biedronka.pl"

    def scrape(self):
        print(f"[Biedronka] Start scraping: {datetime.now().isoformat()}")

        self.ensure_store()
        print(f"[Biedronka] Store ID: {self.store_id}")

        try:
            resp = requests.get(BIEDRONKA_API, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Biedronka] Błąd pobierania API: {e}")
            # Fallback: spróbuj scraping HTML
            return self._scrape_html_fallback()

        items = self._parse_api_response(data)
        return self._save(items)

    def _parse_api_response(self, data: dict) -> list[dict]:
        """Parsuje odpowiedź API Biedronki do listy pozycji."""
        items = []

        # Struktura może się zmieniać — obsługujemy oba warianty
        offers = data.get("offers") or data.get("products") or data.get("items") or []

        for offer in offers:
            try:
                name = (
                    offer.get("name") or
                    offer.get("title") or
                    offer.get("product_name") or ""
                ).strip()

                price_raw = (
                    offer.get("price") or
                    offer.get("promo_price") or
                    offer.get("promotional_price")
                )

                if not name or price_raw is None:
                    continue

                price = float(str(price_raw).replace(",", "."))

                unit = offer.get("unit") or offer.get("unit_of_measure") or "szt"
                unit_amount_raw = offer.get("unit_amount") or offer.get("weight")
                unit_amount = float(unit_amount_raw) if unit_amount_raw else None

                items.append({
                    "store_name": name,
                    "price": price,
                    "unit": unit,
                    "unit_amount": unit_amount,
                    "notes": offer.get("description") or offer.get("label"),
                })
            except (ValueError, TypeError) as e:
                print(f"[Biedronka] Skip offer (parse error): {e}")
                continue

        print(f"[Biedronka] Sparsowano {len(items)} pozycji z API")
        return items

    def _scrape_html_fallback(self) -> dict:
        """Fallback HTML scraping gdy API niedostępne."""
        print("[Biedronka] Fallback HTML scraping...")
        # Stub — implementacja przy potrzebie
        return {"scraped": 0, "prices": 0, "error": "API unavailable, HTML fallback not implemented"}

    def _save(self, items: list[dict]) -> dict:
        if not items:
            print("[Biedronka] Brak pozycji do zapisania")
            return {"scraped": 0, "prices": 0}

        today = datetime.now().strftime("%Y-%m-%d")
        # Biedronka zmienia gazetkę w środę — oblicz najbliższy czwartek -7
        valid_from = today
        valid_to = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        flyer_id = self.upsert_flyer(valid_from, valid_to)
        saved = self.upsert_flyer_items(flyer_id, items)
        prices = self.upsert_prices(items, valid_from, valid_to)

        print(f"[Biedronka] Zapisano: {saved} pozycji gazetki, {prices} cen")
        return {"scraped": saved, "prices": prices}


if __name__ == "__main__":
    BiedronkaScraper().scrape()
