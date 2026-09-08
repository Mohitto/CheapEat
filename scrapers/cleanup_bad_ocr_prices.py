"""
cleanup_bad_ocr_prices.py — jednorazowy skrypt sprzątający.

Pierwsze uruchomienie biedronka/scraper.py (przed dodaniem filtra
prawdopodobieństwa PLAUSIBLE_RANGE_PER_100) zapisało kilka absurdalnych
cen (np. ryż za ~65-100 zł/kg, pomidor za ~50-70 zł/kg, kurczak pierś za
~10 zł/kg) — dokładnie ten sam rodzaj błędu co naprawiliśmy wcześniej w
tej sesji, tylko że tym razem z błędu OCR/dopasowania kontekstu, a nie
złego wzoru. Ten skrypt usuwa WSZYSTKIE ceny source='flyer-ocr' (jeszcze
nie było poprawnego uruchomienia, więc nic wartościowego nie tracimy) —
kolejne odpalenie scrapera (już z filtrem) zapisze je na nowo, tylko
prawdopodobne.
"""
from base_scraper import get_supabase

sb = get_supabase()

res = sb.table("prices").select("id").eq("source", "flyer-ocr").execute()
ids = [row["id"] for row in res.data]
print(f"Znaleziono {len(ids)} cen source='flyer-ocr' do usunięcia")

for price_id in ids:
    sb.table("prices").delete().eq("id", price_id).execute()

print(f"Usunięto {len(ids)} cen")
