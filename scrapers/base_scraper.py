"""Bazowa klasa scrapera — wspólna logika dla wszystkich sklepów."""
import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_or_create(sb: Client, table: str, match: dict, defaults: dict | None = None) -> str:
    """Zwraca ID wiersza pasującego do `match` w `table`, tworząc go z
    `defaults` jeśli jeszcze nie istnieje. Współdzielone przez wszystkie
    scrapery sklepowe (Lidl, Biedronka gazetka, Biedronka sklep, ...)."""
    query = sb.table(table).select("id")
    for key, value in match.items():
        query = query.eq(key, value)
    res = query.limit(1).execute()
    if res.data:
        return res.data[0]["id"]
    ins = sb.table(table).insert({**match, **(defaults or {})}).execute()
    return ins.data[0]["id"]


def replace_price(sb: Client, store_product_id: str, source: str,
                  gross_price: float, valid_from: str, valid_to: str) -> None:
    """Zapisuje cenę produktu, ZASTĘPUJĄC poprzednią z tego samego źródła.

    Scrapery chodzą codziennie; zwykły insert dokładał przy każdym
    przebiegu kolejny wiersz z tą samą kwotą (w bazie znalazło się 16
    identycznych cen jednego sera), przez co tabela `prices` rosła bez
    sensu, a "najnowsza cena" zależała od kolejności sortowania duplikatów.
    """
    sb.table("prices").delete() \
        .eq("store_product_id", store_product_id) \
        .eq("source", source) \
        .execute()
    sb.table("prices").insert({
        "store_product_id": store_product_id,
        "gross_price": gross_price,
        "source": source,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }).execute()


class BaseScraper:
    store_name: str = ""
    store_website: str = ""

    def __init__(self):
        self.sb = get_supabase()
        self.store_id: str | None = None

    def ensure_store(self) -> str:
        """Zwraca ID sklepu z Supabase. Tworzy jeśli nie istnieje."""
        res = self.sb.table("stores") \
            .select("id") \
            .eq("name", self.store_name) \
            .limit(1) \
            .execute()

        if res.data:
            self.store_id = res.data[0]["id"]
        else:
            ins = self.sb.table("stores").insert({
                "name": self.store_name,
                "website_url": self.store_website,
                "is_active": True,
            }).execute()
            self.store_id = ins.data[0]["id"]

        return self.store_id

    def upsert_flyer(self, valid_from: str, valid_to: str, file_url: str | None = None) -> str:
        """Tworzy lub aktualizuje gazetkę. Zwraca ID."""
        res = self.sb.table("flyers").upsert({
            "store_id": self.store_id,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "file_url": file_url,
        }, on_conflict="store_id,valid_from").execute()
        return res.data[0]["id"]

    def upsert_flyer_items(self, flyer_id: str, items: list[dict]) -> int:
        """Wstawia pozycje gazetki. Zwraca liczbę wstawionych."""
        if not items:
            return 0

        # Dodaj flyer_id do każdej pozycji
        for item in items:
            item["flyer_id"] = flyer_id

        res = self.sb.table("flyer_items").upsert(
            items,
            on_conflict="flyer_id,store_name"
        ).execute()
        return len(res.data)

    def upsert_prices(self, items: list[dict], valid_from: str, valid_to: str) -> int:
        """Wstawia ceny do tabeli prices (source='flyer')."""
        if not items:
            return 0

        price_rows = []
        for item in items:
            # Szukaj store_product po nazwie
            prod = self.sb.table("store_products") \
                .select("id") \
                .eq("store_id", self.store_id) \
                .ilike("name", f"%{item['store_name']}%") \
                .limit(1) \
                .execute()

            if prod.data:
                price_rows.append({
                    "store_product_id": prod.data[0]["id"],
                    "gross_price": item["price"],
                    "source": "flyer",
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                })

        if price_rows:
            self.sb.table("prices").upsert(
                price_rows,
                on_conflict="store_product_id,source,valid_from"
            ).execute()

        return len(price_rows)

    def scrape(self):
        raise NotImplementedError
