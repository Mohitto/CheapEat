"""Czyści stare, niepoprawnie zescrapowane przepisy (source='aniagotuje' z
lipca — brak/niepełne recipe_ingredients, nie dają się wycenić).

Soft-delete: ustawia deleted_at zamiast trwale kasować wiersz — FeedScreen
filtruje `.is('deleted_at', null)`, więc znikają z apki natychmiast, ale
dane zostają w bazie na wypadek gdyby jednak się przydały (np. do ponownego
sparsowania składników w przyszłości).
"""
from datetime import datetime, timezone

from base_scraper import get_supabase

sb = get_supabase()


def main():
    now = datetime.now(timezone.utc).isoformat()

    res = sb.table("recipes").select("id, title").eq("source", "aniagotuje").is_("deleted_at", "null").execute()
    rows = res.data or []
    print(f"Do usunięcia (soft-delete): {len(rows)} przepisów źle zescrapowanych (source=aniagotuje)")

    if not rows:
        print("Nic do zrobienia.")
        return

    ids = [r["id"] for r in rows]
    # Update w partiach po 100, żeby nie przekroczyć limitu URL/query
    updated = 0
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        sb.table("recipes").update({"deleted_at": now}).in_("id", batch).execute()
        updated += len(batch)

    print(f"Soft-deleted: {updated} przepisów.")


if __name__ == "__main__":
    main()
