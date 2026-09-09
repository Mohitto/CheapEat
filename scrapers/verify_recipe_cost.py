"""
verify_recipe_cost.py — jednorazowy skrypt weryfikacyjny.

Apka to czysty React Native CLI (bez Expo) — w tym środowisku (headless,
bez Android SDK/emulatora, bez Xcode) nie da się uruchomić UI i zobaczyć
przepisu "na żywo" tak jak w telefonie. Ten skrypt liczy koszt przepisu
DOKŁADNIE tym samym algorytmem co src/services/recipeService.ts +
priceService.ts + ingredientService.ts, ale bezpośrednio na Supabase
(prawdziwe dane po scraperach), żeby potwierdzić że liczby faktycznie
przepływają od zescrapowanej ceny do kosztu przepisu — bez czekania na
telefon/emulator.

Odtworzona logika (musi zostać zsynchronizowana ręcznie, jeśli TS się
zmieni — to jednorazowy skrypt diagnostyczny, nie część aplikacji):
- calculateRecipeCost (recipeService.ts): dla każdego składnika przepisu
  (poza IGNORED_IN_COST, np. "sól" — te w ogóle pomijamy, bez sprawdzania
  ceny) sprawdza WSZYSTKIE ingredient_mappings i wybiera opcję z
  najniższym kosztem CAŁYCH opakowań potrzebnych do pokrycia przepisu
  (packagesNeeded * cena opakowania) — NIE ułamek proporcjonalny do
  ilości (składników nie da się kupić "dokładnie na wagę"; 30g masła
  oznacza kupno całej kostki, np. 200g). Koszt całkowity/na porcję
  pokazujemy, gdy CHOCIAŻ JEDEN składnik ma cenę (hasAnyCost) — nie
  wymagamy już 100% pokrycia (patrz commit wprowadzający
  IGNORED_IN_COST/hasAnyCost).
- getCurrentPrice (priceService.ts): najpierw source='flyer' z
  valid_to >= dziś, inaczej najnowszy wpis wg updated_at. Realne
  scrapery piszą source='flyer-ocr'/'flyer-ssr'/'shop-regular' (nie
  dosłownie 'flyer'), więc w praktyce zawsze trafia gałąź fallback — to
  obserwacja o faktycznym zachowaniu apki, nie coś co ten skrypt naprawia.
- packagesNeeded (ingredientService.ts): ceil(amount / unitAmount), gdzie
  unitAmount = conversion_factor * 100 (gramatura/pojemność opakowania).
"""
import math
import sys
from datetime import datetime, timezone

from base_scraper import get_supabase

sb = get_supabase()

IGNORED_IN_COST = {"sól"}


def get_current_price(store_product_id: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    flyer = sb.table("prices").select("*") \
        .eq("store_product_id", store_product_id) \
        .eq("source", "flyer") \
        .gte("valid_to", today) \
        .execute()
    if flyer.data:
        latest = sorted(flyer.data, key=lambda r: r.get("updated_at") or r.get("created_at") or "")[-1]
        return latest.get("gross_price"), latest.get("source")

    all_prices = sb.table("prices").select("*") \
        .eq("store_product_id", store_product_id).execute()
    if all_prices.data:
        latest = sorted(all_prices.data, key=lambda r: r.get("updated_at") or r.get("created_at") or "")[-1]
        return latest.get("gross_price"), latest.get("source")
    return None, None


def calculate_recipe_cost(recipe_title_like: str):
    recipe_res = sb.table("recipes").select("*").ilike("title", f"%{recipe_title_like}%").limit(1).execute()
    if not recipe_res.data:
        print(f"Nie znaleziono przepisu pasującego do '{recipe_title_like}'")
        return
    recipe = recipe_res.data[0]
    print(f"\n=== Przepis: {recipe['title']} ({recipe.get('portions', 1)} porcje) ===")

    ri_res = sb.table("recipe_ingredients").select("*").eq("recipe_id", recipe["id"]).execute()

    total_cost = 0.0
    has_any_cost = False
    lines = []

    for ri in ri_res.data:
        ing_res = sb.table("ingredients").select("*").eq("id", ri["ingredient_id"]).execute()
        ingredient_name = ing_res.data[0]["name"] if ing_res.data else ri["ingredient_id"]
        amount = ri["amount"]

        if ingredient_name in IGNORED_IN_COST:
            lines.append(f"  · {ingredient_name} ({amount}{ri['unit']}): pominięty (przyprawa)")
            continue

        mappings_res = sb.table("ingredient_mappings").select("*") \
            .eq("ingredient_id", ri["ingredient_id"]).order("priority").execute()

        best_cost = None
        best_price = None
        best_store = None
        best_source = None
        best_packages = None
        best_unit_amount = None

        best_product = None

        for mapping in mappings_res.data:
            store_product_id = mapping["store_product_id"]
            price, source = get_current_price(store_product_id)
            if price is None:
                continue

            sp_res = sb.table("store_products").select("*, stores(name)").eq("id", store_product_id).execute()
            if not sp_res.data:
                continue
            sp = sp_res.data[0]

            # Jednostka i wielkość opakowania idą z produktu sklepowego;
            # opakowanie w innej jednostce niż przepis pomijamy (nie ma
            # bezpiecznego przelicznika gramy <-> sztuki).
            unit_amount = sp.get("unit_amount") or 0
            if unit_amount <= 0 or sp.get("unit") != ri["unit"]:
                continue

            packages = math.ceil(amount / unit_amount)
            candidate_cost = packages * price

            if best_cost is None or candidate_cost < best_cost:
                best_cost = candidate_cost
                best_price = price
                best_source = source
                best_packages = packages
                best_unit_amount = unit_amount
                best_product = sp["name"]
                store_info = sp.get("stores")
                best_store = store_info["name"] if store_info else None

        if best_cost is None:
            lines.append(f"  ✗ {ingredient_name} ({amount} {ri['unit']}): BRAK CENY")
        else:
            has_any_cost = True
            total_cost += best_cost
            lines.append(
                f"  ✓ {ingredient_name} ({amount} {ri['unit']}): {best_cost:.2f} zł\n"
                f"      kup {best_packages}x '{best_product}' "
                f"({best_unit_amount:g} {ri['unit']} @ {best_price} zł) "
                f"[{best_store}, source={best_source}]"
            )

    for line in lines:
        print(line)

    portions = recipe.get("portions") or 1
    if has_any_cost:
        print(f"\nKOSZT CAŁKOWITY (częściowy jeśli brakuje cen powyżej): {round(total_cost, 2)} zł")
        print(f"KOSZT NA PORCJĘ: {round(total_cost / portions, 2)} zł")
    else:
        print("\nKOSZT: brak (żaden składnik nie ma ceny)")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["Naleśniki", "Omlet"]
    for t in targets:
        calculate_recipe_cost(t)
