"""
cleanup_seed_prices.py — jednorazowy skrypt sprzątający.

seed_dev_data.py (i nieużywana już klasa BaseScraper.upsert_prices)
zapisują ceny z literalnym source='flyer' — placeholder na potrzeby
developmentu, zanim istniały prawdziwe scrapery. Prawdziwe scrapery
(Biedronka, Lidl) używają source='flyer-ocr'/'flyer-ssr'.

Problem: calculateRecipeCost w apce wybiera NAJTAŃSZĄ opcję spośród
wszystkich ingredient_mappings dla składnika — jeśli stara cena seed
(source='flyer') jest tańsza niż realna zescrapowana, apka pokaże
starą, mimo że w bazie jest już prawdziwa. Ten skrypt usuwa WSZYSTKIE
ceny source='flyer', żeby apka liczyła koszt wyłącznie z realnych
danych (flyer-ocr/flyer-ssr).
"""
from base_scraper import get_supabase

sb = get_supabase()

res = sb.table("prices").select("id").eq("source", "flyer").execute()
ids = [row["id"] for row in res.data]
print(f"Znaleziono {len(ids)} cen source='flyer' (dane seed) do usunięcia")

for price_id in ids:
    sb.table("prices").delete().eq("id", price_id).execute()

print(f"Usunięto {len(ids)} cen")
