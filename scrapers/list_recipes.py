"""Diagnostyka: wypisuje wszystkie przepisy z tabeli `recipes` w Supabase.

Nie modyfikuje niczego — czysty odczyt, do zdiagnozowania skąd się biorą
przepisy pokazujące się w apce poza tymi wstawionymi przez seed_dev_data.py.
"""
from base_scraper import get_supabase

sb = get_supabase()


def main():
    res = sb.table("recipes").select(
        "id, title, source, source_url, image_url, is_public, deleted_at, scraped_at, created_by"
    ).order("scraped_at", desc=True).execute()

    rows = res.data or []
    print(f"== {len(rows)} przepisów w tabeli recipes ==\n")
    for r in rows:
        print(
            f"- {r.get('title')!r} | source={r.get('source')!r} | "
            f"is_public={r.get('is_public')} | deleted_at={r.get('deleted_at')} | "
            f"image_url={'TAK' if r.get('image_url') else 'brak'} | "
            f"scraped_at={r.get('scraped_at')} | id={r.get('id')}"
        )

    print("\n== Ile przepisów per source ma powiązane recipe_ingredients ==")
    by_source: dict[str, dict[str, int]] = {}
    for r in rows:
        src = r.get("source") or "?"
        by_source.setdefault(src, {"total": 0, "with_ingredients": 0})
        by_source[src]["total"] += 1

    ri_res = sb.table("recipe_ingredients").select("recipe_id").execute()
    recipe_ids_with_ingredients = {row["recipe_id"] for row in (ri_res.data or [])}

    for r in rows:
        src = r.get("source") or "?"
        if r.get("id") in recipe_ids_with_ingredients:
            by_source[src]["with_ingredients"] += 1

    for src, counts in by_source.items():
        print(f"  {src}: {counts['with_ingredients']}/{counts['total']} ma recipe_ingredients")


if __name__ == "__main__":
    main()
