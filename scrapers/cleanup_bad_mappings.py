"""
cleanup_bad_mappings.py — usuwa z bazy błędne i martwe dane cenowe.

Poprawki w scraperach (INGREDIENT_EXCLUDE_KEYWORDS, jednostki sztukowe)
działają tylko na NOWO zapisywane wiersze. Produkty zapisane wcześniej
zostają w bazie i dalej biorą udział w wyborze "najtańszej opcji" — stąd
sałatka jajecznaLisnera (5,99 zł / 500 g) udawała w apce jajka, a pasztet
z pomidorami udawał pomidora.

Usuwamy trzy rodzaje śmieci:
1. Produkty, których nazwa NIE jest już dopasowywana do składnika, do
   którego są zmapowane (czyli takie, których dzisiejszy match_ingredient
   nie zaakceptowałby) — łącznie z ich mapowaniami i cenami.
2. Zduplikowane ceny: to samo (store_product, source) wielokrotnie —
   zostaje tylko najnowsza (scraper robił kiedyś insert zamiast replace).
3. Mapowania-sieroty: wskazujące na produkty bez żadnej ceny (pozostałości
   po seedzie), przez które apka liczyła pokrycie sklepów z powietrza.
4. Ceny gazetkowe absurdalnie niskie wobec ceny REGULARNEJ tego samego
   składnika — mięso mielone po 0,50 zł/100 g przy regularnych 3,12 to nie
   promocja, tylko zły odczyt OCR. Scraper stosuje dziś tę samą regułę
   przy zapisie, ale wiersze zapisane wcześniej same z bazy nie znikną.

Skrypt jest idempotentny — można go puścić wielokrotnie.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_scraper import get_supabase
from ingredient_catalog import match_ingredient, unit_price_of

sb = get_supabase()

# Sufiksy dodawane przez nasze scrapery do nazw produktów — przy
# sprawdzaniu dopasowania trzeba je odciąć, bo to nie część nazwy ze sklepu.
NAME_SUFFIXES = [
    " (Biedronka, cena regularna)",
    " (Lidl)",
]


def strip_suffix(name: str) -> str:
    for suffix in NAME_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def cleanup_mismatched_products() -> int:
    """Produkty zmapowane do składnika, do którego dziś by nie pasowały."""
    removed = 0
    ingredients = {i["id"]: i["name"] for i in sb.table("ingredients").select("*").execute().data}
    mappings = sb.table("ingredient_mappings").select("*").execute().data

    for m in mappings:
        ing_name = ingredients.get(m["ingredient_id"])
        if not ing_name:
            continue

        sp = sb.table("store_products").select("*").eq("id", m["store_product_id"]).execute().data
        if not sp:
            continue
        product_name = sp[0]["name"]

        # Produkty gazetkowe mają nazwę generowaną przez nas, nie nazwę
        # handlową — te zostawiamy. Dopasowujemy po samym "(gazetka",
        # bo nazwa opisuje też wariant oferty: "Masło Biedronka
        # (gazetka, 5x200g po 1.99 zł, z kartą)".
        if "(gazetka" in product_name:
            continue

        matched = match_ingredient(strip_suffix(product_name))
        if matched == ing_name:
            continue

        print(f"USUWAM: '{product_name}' był zmapowany jako '{ing_name}', "
              f"a dziś pasuje do '{matched}'")
        sb.table("prices").delete().eq("store_product_id", m["store_product_id"]).execute()
        sb.table("ingredient_mappings").delete().eq("id", m["id"]).execute()
        sb.table("store_products").delete().eq("id", m["store_product_id"]).execute()
        removed += 1

    return removed


def cleanup_duplicate_prices() -> int:
    """Zostawia tylko najnowszą cenę dla każdej pary (produkt, source)."""
    removed = 0
    prices = sb.table("prices").select("*").execute().data

    groups: dict[tuple[str, str], list[dict]] = {}
    for pr in prices:
        groups.setdefault((pr["store_product_id"], pr["source"]), []).append(pr)

    for (spid, source), rows in groups.items():
        if len(rows) <= 1:
            continue
        rows.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "")
        for stale in rows[:-1]:
            sb.table("prices").delete().eq("id", stale["id"]).execute()
            removed += 1
        print(f"USUWAM {len(rows) - 1} duplikatów ceny (produkt {spid}, source={source})")

    return removed


def cleanup_priceless_mappings() -> int:
    """Mapowania do produktów, które nie mają żadnej ceny."""
    removed = 0
    mappings = sb.table("ingredient_mappings").select("*").execute().data

    for m in mappings:
        prices = sb.table("prices").select("id").eq("store_product_id", m["store_product_id"]) \
            .limit(1).execute().data
        if prices:
            continue

        sp = sb.table("store_products").select("name").eq("id", m["store_product_id"]).execute().data
        name = sp[0]["name"] if sp else m["store_product_id"]
        print(f"USUWAM mapowanie bez ceny: '{name}'")
        sb.table("ingredient_mappings").delete().eq("id", m["id"]).execute()
        sb.table("store_products").delete().eq("id", m["store_product_id"]).execute()
        removed += 1

    return removed


MIN_PROMO_FRACTION_OF_REGULAR = 0.30


def cleanup_implausible_promos() -> int:
    """Ceny z gazetki poniżej 30% ceny regularnej tej samej kategorii."""
    removed = 0
    ingredients = {i["id"]: i["name"] for i in sb.table("ingredients").select("*").execute().data}

    for ingredient_id, ingredient_name in ingredients.items():
        mappings = sb.table("ingredient_mappings").select("store_product_id") \
            .eq("ingredient_id", ingredient_id).execute().data
        if not mappings:
            continue

        offers = []
        for mapping in mappings:
            sp = sb.table("store_products").select("id,name,unit,unit_amount") \
                .eq("id", mapping["store_product_id"]).limit(1).execute().data
            if not sp:
                continue
            product = sp[0]
            unit, unit_amount = product.get("unit"), product.get("unit_amount")
            if not unit or not unit_amount or unit_amount <= 0:
                continue
            for row in sb.table("prices").select("id,gross_price,source") \
                    .eq("store_product_id", product["id"]).execute().data:
                unit_price = unit_price_of(ingredient_name, row["gross_price"], unit, unit_amount)
                if unit_price is not None:
                    offers.append({**row, "unit_price": unit_price, "product": product["name"]})

        regular = [o["unit_price"] for o in offers if o["source"] == "shop-regular"]
        if not regular:
            continue
        floor = min(regular) * MIN_PROMO_FRACTION_OF_REGULAR

        for offer in offers:
            if offer["source"] == "shop-regular" or offer["unit_price"] >= floor:
                continue
            print(f"USUWAM CENĘ: {ingredient_name} '{offer['product']}' "
                  f"{offer['gross_price']} zł = {round(offer['unit_price'], 3)} zł/j., "
                  f"czyli {offer['unit_price'] / min(regular):.0%} ceny regularnej")
            sb.table("prices").delete().eq("id", offer["id"]).execute()
            removed += 1

    return removed


if __name__ == "__main__":
    print("=== 1. Produkty zmapowane do złego składnika ===")
    bad = cleanup_mismatched_products()
    print(f"-> usunięto {bad}\n")

    print("=== 2. Zduplikowane ceny ===")
    dupes = cleanup_duplicate_prices()
    print(f"-> usunięto {dupes}\n")

    print("=== 3. Mapowania do produktów bez ceny ===")
    orphans = cleanup_priceless_mappings()
    print(f"-> usunięto {orphans}\n")

    # Na końcu, bo ta kontrola porównuje się z cenami REGULARNYMI — a te
    # muszą już być posprzątane z produktów zmapowanych do złej kategorii,
    # inaczej porównywalibyśmy promocję z ceną zupełnie innego produktu.
    print("=== 4. Ceny gazetkowe absurdalnie niskie wobec regularnych ===")
    absurd = cleanup_implausible_promos()
    print(f"-> usunięto {absurd}\n")

    print(f"RAZEM: {bad} złych produktów, {dupes} duplikatów cen, "
          f"{orphans} mapowań bez ceny, {absurd} nierealnych promocji")
