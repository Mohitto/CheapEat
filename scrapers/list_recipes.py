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


if __name__ == "__main__":
    main()
