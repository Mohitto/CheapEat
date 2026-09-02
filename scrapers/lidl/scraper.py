"""Scraper gazetki Lidl.

UWAGA: to jest best-effort szkielet napisany BEZ dostępu do internetu (sesja,
w której to powstało, ma zablokowany ruch do lidl.pl). LIDL_API poniżej to
zgadywanka na wzór biedronka/scraper.py, prawdopodobnie zła. Struktura kodu
(fetch -> dump w trybie debug -> parsuj -> zapisz) jest identyczna jak w
scraperze Biedronki celowo, żeby dało się to naprawić w 5 minut, kiedy
zobaczymy realną odpowiedź.

Jak naprawić:
1. `export SCRAPER_DEBUG=1`
2. `python -m lidl.scraper` (lokalnie, z realnym internetem) albo odpal przez
   GitHub Actions
3. Sprawdź debug_lidl_*.txt — jeśli LIDL_API zwróci 404/HTML zamiast JSON,
   podmień URL na prawdziwy (widoczny np. w devtools -> Network na
   lidl.pl/pl/c/gazetka podczas ładowania promocji)
4. Dopasuj klucze w _parse_api_response do realnego JSON-a
"""
import json
import os
import sys
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_scraper import BaseScraper

DEBUG = os.environ.get("SCRAPER_DEBUG") == "1"

# Zgadywanka — nie zweryfikowana. Alternatywa do sprawdzenia: strona gazetki
# https://www.lidl.pl/c/gazetka (HTML) jeśli nie ma osobnego API.
LIDL_API = "https://www.lidl.pl/pl/api/offers"
LIDL_HOMEPAGE = "https://www.lidl.pl/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CheapEatBot/1.0)",
    "Accept": "application/json",
    "Accept-Language": "pl-PL,pl;q=0.9",
}


def _dump_debug(name: str, content: str) -> None:
    path = f"debug_{name}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content[:20000])
    print(f"[DEBUG] Zapisano surową odpowiedź do {path} (pierwsze 20000 znaków)")
    print(f"[DEBUG] Podgląd (500 znaków): {content[:500]!r}")


class LidlScraper(BaseScraper):
    store_name = "Lidl"
    store_website = "https://www.lidl.pl"

    def scrape(self):
        print(f"[Lidl] Start scraping: {datetime.now().isoformat()}")

        self.ensure_store()
        print(f"[Lidl] Store ID: {self.store_id}")

        try:
            resp = requests.get(LIDL_API, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            if DEBUG:
                _dump_debug("lidl_api_response", resp.text)
            data = resp.json()
        except Exception as e:
            print(f"[Lidl] Błąd pobierania/parsowania JSON z {LIDL_API}: {e}")
            try:
                _dump_debug("lidl_api_error_body", resp.text)
            except NameError:
                pass
            return self._scrape_html_fallback()

        items = self._parse_api_response(data)
        if not items and DEBUG:
            print("[Lidl] 0 pozycji sparsowanych mimo poprawnej odpowiedzi JSON —")
            print("[Lidl] sprawdź debug_lidl_api_response.txt, klucze w _parse_api_response nie pasują do realnej struktury.")
        return self._save(items)

    def _parse_api_response(self, data) -> list[dict]:
        """Parsuje odpowiedź API Lidla do listy pozycji.

        Klucze zgadywane na wzór typowych API sklepowych (jak w
        biedronka/scraper.py) — obsługujemy kilka wariantów nazw, ale
        realny kształt trzeba zweryfikować na żywej odpowiedzi.
        """
        items = []

        if isinstance(data, dict):
            offers = data.get("offers") or data.get("products") or data.get("items") or []
        elif isinstance(data, list):
            offers = data
        else:
            offers = []

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
            except (ValueError, TypeError, AttributeError) as e:
                print(f"[Lidl] Skip offer (parse error): {e}")
                continue

        print(f"[Lidl] Sparsowano {len(items)} pozycji z API")
        return items

    def _scrape_html_fallback(self) -> dict:
        """Fallback: pobiera stronę główną jako HTML i zapisuje do pliku.

        Celowo nie parsuje HTML — struktura strony nieznana bez realnego
        dostępu. Zrzuca surową odpowiedź, żeby dało się znaleźć prawdziwy
        link/endpoint gazetki i napisać parser na tej podstawie.
        """
        print("[Lidl] Fallback: pobieram HTML strony głównej...")
        try:
            resp = requests.get(
                LIDL_HOMEPAGE,
                headers={**HEADERS, "Accept": "text/html"},
                timeout=30,
            )
            resp.raise_for_status()
            _dump_debug("lidl_html_fallback", resp.text)
        except Exception as e:
            print(f"[Lidl] Fallback HTML też zawiódł: {e}")
            return {"scraped": 0, "prices": 0, "error": str(e)}

        return {"scraped": 0, "prices": 0, "error": "HTML fallback: zrzucono stronę, parser jeszcze nie napisany"}

    def _save(self, items: list[dict]) -> dict:
        if not items:
            print("[Lidl] Brak pozycji do zapisania")
            return {"scraped": 0, "prices": 0}

        today = datetime.now().strftime("%Y-%m-%d")
        valid_from = today
        valid_to = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        flyer_id = self.upsert_flyer(valid_from, valid_to)
        saved = self.upsert_flyer_items(flyer_id, items)
        prices = self.upsert_prices(items, valid_from, valid_to)

        print(f"[Lidl] Zapisano: {saved} pozycji gazetki, {prices} cen")
        return {"scraped": saved, "prices": prices}


if __name__ == "__main__":
    LidlScraper().scrape()
