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

Skrypt jest idempotentny — można go puścić wielokrotnie.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_scraper import get_supabase
from ingredient_catalog import match_ingredient

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

    print(f"RAZEM: {bad} złych produktów, {dupes} duplikatów cen, {orphans} mapowań bez ceny")
