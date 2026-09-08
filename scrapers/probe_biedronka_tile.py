"""
probe_biedronka_tile.py — czwarta runda sondy.

Kategoria /nabial/mleko/ na zakupy.biedronka.pl pokazuje realne ceny
(3,49–11,50 zł) i linki produktowe z opisowym slugiem zawierającym
markę+nazwę+gramaturę+PID (np. mlekovita-...-32-1-l-0000007074.html).
Ta sonda wycina surowy fragment HTML wokół jednego konkretnego
data-pid, żeby zobaczyć DOKŁADNĄ strukturę "kafelka" produktu (gdzie
dokładnie jest nazwa, cena, gramatura) — do zbudowania precyzyjnego
parsera zamiast zgadywania na podstawie samych regexów na cały tekst.
"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}

URL = "https://zakupy.biedronka.pl/nabial/mleko/"
TARGET_PID = "0000007074"  # Mlekovita mleko spożywcze polskie 3,2% 1 l


def main():
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    html = resp.text
    print(f"{URL} -> status {resp.status_code}, długość {len(html)}")

    idx = html.find(TARGET_PID)
    if idx == -1:
        print(f"Nie znaleziono PID {TARGET_PID} w HTML")
        return

    # Wytnij spory kontekst wokół (kafelek produktu to zwykle >1000 znaków
    # z klasami CSS, obrazkiem, nazwą, ceną, przyciskiem "dodaj do koszyka").
    start = max(0, idx - 2500)
    end = min(len(html), idx + 2500)
    print(f"\n=== Kontekst wokół PID {TARGET_PID} (znaki {start}-{end}) ===")
    print(html[start:end])


if __name__ == "__main__":
    main()
