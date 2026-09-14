"""
diagnose_prices.py — pełny zrzut stanu cen dla śledzonych składników.

Odpowiada na pytanie "skąd apka bierze TAKĄ cenę": dla każdego składnika
wypisuje WSZYSTKIE zmapowane produkty sklepowe (nazwa, jednostka,
gramatura opakowania, conversion_factor) i WSZYSTKIE ich ceny (kwota,
source, okno ważności) — czyli dokładnie te dane, z których
recipeService.ts liczy koszt przepisu.

Potrzebne, bo poprawki w scraperach (np. INGREDIENT_EXCLUDE_KEYWORDS)
działają tylko na NOWO zapisywane wiersze — stare, błędne produkty i
mapowania zostają w bazie i dalej wygrywają wybór "najtańszej opcji".
"""
import sys

from base_scraper import get_supabase

sb = get_supabase()


def dump_ingredients() -> None:
    ing_res = sb.table("ingredients").select("*").execute()
    ingredients = sorted(ing_res.data, key=lambda i: i["name"])
    print(f"### Składników w bazie: {len(ingredients)}\n")

    for ing in ingredients:
        maps = sb.table("ingredient_mappings").select("*") \
            .eq("ingredient_id", ing["id"]).order("priority").execute().data
        if not maps:
            print(f"=== {ing['name']}: BRAK MAPOWAŃ ===")
            continue

        print(f"=== {ing['name']} ({len(maps)} mapowań) ===")
        for m in maps:
            spid = m["store_product_id"]
            sp_res = sb.table("store_products").select("*, stores(name)").eq("id", spid).execute()
            if not sp_res.data:
                print(f"  [!] mapowanie -> nieistniejący store_product {spid}")
                continue
            p = sp_res.data[0]
            store = (p.get("stores") or {}).get("name")
            print(f"  - '{p['name']}' [{store}]")
            print(f"      unit={p.get('unit')} unit_amount={p.get('unit_amount')} "
                  f"conversion_factor={m.get('conversion_factor')} priority={m.get('priority')}")

            prices = sb.table("prices").select("*").eq("store_product_id", spid).execute().data
            if not prices:
                print("      (brak cen)")
            for pr in sorted(prices, key=lambda r: r.get("updated_at") or r.get("created_at") or ""):
                print(f"      {pr['gross_price']} zł  source={pr['source']}  "
                      f"ważna {pr.get('valid_from')}..{pr.get('valid_to')}  "
                      f"updated={pr.get('updated_at')}")
        print()


def dump_recipes() -> None:
    print("\n### Składniki testowych przepisów (amount + unit tak jak w bazie)\n")
    recipes = sb.table("recipes").select("*").ilike("title", "%[TEST]%").execute().data
    for r in recipes:
        print(f"=== {r['title']} ({r.get('portions')} porcji) ===")
        ris = sb.table("recipe_ingredients").select("*").eq("recipe_id", r["id"]).execute().data
        for ri in ris:
            ing = sb.table("ingredients").select("name").eq("id", ri["ingredient_id"]).execute().data
            name = ing[0]["name"] if ing else ri["ingredient_id"]
            print(f"  {name}: amount={ri['amount']} unit={ri['unit']!r}")
        print()


if __name__ == "__main__":
    dump_ingredients()
    dump_recipes()
