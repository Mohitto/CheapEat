"""
seed_dev_data.py — dane testowe do sprawdzenia PEŁNEGO przepływu w apce:
przepis -> mapowanie składnik/produkt -> cena z gazetki -> koszt zakupów.

To NIE jest prawdziwy scraping. To ręcznie wpisane dane startowe, żeby dało
się przetestować UI (Feed -> szczegóły przepisu -> koszt / koszyk) zanim
scrapery Biedronki/Lidla i scraper przepisów (aniagotuje.pl) są gotowe do
produkcji. Przepisy są oznaczone prefiksem "[TEST]" i source="seed-dev-data",
żeby łatwo je odróżnić i później usunąć.

WAŻNE: nazwy kolumn w tabelach Supabase (`recipes`, `store_products`, ...)
zostały wywnioskowane z kodu aplikacji (FeedScreen.tsx, AGENT_CONTEXT.md),
nie zweryfikowane bezpośrednio na żywej bazie. Jeśli insert wywali się
błędem PostgREST wskazującym konkretną kolumnę — daj znać, poprawka jest
zwykle trywialna.

Uruchomienie:
    cd scrapers
    cp .env.example .env   # uzupełnij SUPABASE_URL i SUPABASE_SERVICE_KEY (service role!)
    pip install -r requirements.txt
    python seed_dev_data.py
"""
from datetime import datetime

from base_scraper import get_supabase

sb = get_supabase()


def get_or_create(table: str, match: dict, defaults: dict | None = None) -> str:
    """Zwraca id wiersza pasującego do `match`, albo tworzy nowy (idempotentne)."""
    query = sb.table(table).select("id")
    for key, value in match.items():
        query = query.eq(key, value)
    res = query.limit(1).execute()
    if res.data:
        return res.data[0]["id"]
    ins = sb.table(table).insert({**match, **(defaults or {})}).execute()
    return ins.data[0]["id"]


# (nazwa składnika, białko/100g, kcal/100g)
INGREDIENTS = [
    ("mąka pszenna", 10.0, 364),
    ("jajka", 12.5, 143),
    ("mleko", 3.3, 61),
    ("cukier", 0.0, 400),
    ("masło", 0.8, 717),
    ("ryż", 7.0, 130),
    ("kurczak pierś", 23.0, 165),
    ("cebula", 1.1, 40),
    ("pomidor", 0.9, 18),
    ("ser żółty", 25.0, 350),
    ("olej rzepakowy", 0.0, 884),
    ("sól", 0.0, 0),
]

RECIPES = [
    {
        "title": "[TEST] Kurczak z ryżem i warzywami",
        "portions": 2,
        "prep_minutes": 30,
        "ingredients": [
            ("kurczak pierś", 400, "g"),
            ("ryż", 200, "g"),
            ("cebula", 100, "g"),
            ("pomidor", 150, "g"),
            ("olej rzepakowy", 20, "g"),
            ("sól", 5, "g"),
        ],
    },
    {
        "title": "[TEST] Naleśniki",
        "portions": 4,
        "prep_minutes": 20,
        "ingredients": [
            ("mąka pszenna", 250, "g"),
            ("mleko", 500, "ml"),
            # Jajka liczymy w sztukach — nikt nie kupuje ani nie odmierza
            # ich na gramy (patrz INGREDIENT_UNIT w ingredient_catalog.py).
            ("jajka", 2, "szt"),
            ("masło", 30, "g"),
            ("sól", 3, "g"),
        ],
    },
    {
        "title": "[TEST] Omlet z serem",
        "portions": 2,
        "prep_minutes": 10,
        "ingredients": [
            ("jajka", 3, "szt"),
            ("mleko", 50, "ml"),
            ("ser żółty", 60, "g"),
            ("masło", 15, "g"),
            ("sól", 2, "g"),
        ],
    },
]


def main():
    print("== Sklepy ==")
    store_ids = {}
    for name, url in [("Biedronka", "https://www.biedronka.pl"), ("Lidl", "https://www.lidl.pl")]:
        store_ids[name] = get_or_create("stores", {"name": name}, {"website_url": url, "is_active": True})
    print(f"  {list(store_ids.keys())}")

    print("== Składniki ==")
    ingredient_ids = {}
    for name, protein, kcal in INGREDIENTS:
        ingredient_ids[name] = get_or_create(
            "ingredients", {"name": name},
            {"protein_per_100g": protein, "kcal_per_100g": kcal},
        )
    print(f"  {len(ingredient_ids)} składników")

    # Produktów sklepowych, mapowań i cen NIE seedujemy. Wcześniej ten
    # skrypt wstawiał zmyślone ceny (source='flyer') razem ze zmyślonymi
    # opakowaniami; potrafiły wygrać z prawdziwymi cenami ze scraperów
    # (apka wybiera najtańszą opcję) i pokazywały w przepisie kwoty, które
    # nie istnieją w żadnym sklepie. Ceny mają jedno źródło: scrapery.

    print("== Przepisy testowe ==")
    for recipe in RECIPES:
        recipe_id = get_or_create(
            "recipes", {"title": recipe["title"]},
            {
                "portions": recipe["portions"],
                "prep_minutes": recipe["prep_minutes"],
                "is_public": True,
                "source": "seed-dev-data",
                "scraped_at": datetime.now().isoformat(),
            },
        )
        for ing_name, amount, unit in recipe["ingredients"]:
            existing = sb.table("recipe_ingredients").select("id") \
                .eq("recipe_id", recipe_id) \
                .eq("ingredient_id", ingredient_ids[ing_name]).limit(1).execute()
            payload = {
                "recipe_id": recipe_id,
                "ingredient_id": ingredient_ids[ing_name],
                "amount": amount,
                "unit": unit,
            }
            if existing.data:
                # Aktualizuj — żeby ponowne odpalenie skryptu zbiegało do
                # aktualnej definicji (np. poprawka jednostki), a nie tylko
                # wstawiało raz i nigdy więcej nie dotykało wiersza.
                sb.table("recipe_ingredients").update(payload).eq("id", existing.data[0]["id"]).execute()
            else:
                sb.table("recipe_ingredients").insert(payload).execute()
        print(f"  {recipe['title']}")

    print("\nGotowe. W apce: Feed -> [TEST] ... -> sprawdź, czy liczy się koszt.")


if __name__ == "__main__":
    main()
