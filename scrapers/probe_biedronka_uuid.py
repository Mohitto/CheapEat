"""
probe_biedronka_uuid.py — jednorazowy skrypt diagnostyczny.

probe_biedronka_network.py (Playwright) ustalił, że prawdziwe dane
gazetki (obrazki stron) pochodzą z:
  https://leaflet-api.prod.biedronka.cloud/api/leaflets/{UUID}?ctx=web
i że stronę ładuje widget https://cdn.biedronka.cloud/leaflet-widget/index.js.

Pytanie: skąd widget bierze {UUID}? Jeśli jest zaszyty w statycznym HTML-u
strony press,id,... (np. jako atrybut custom elementu), to produkcyjny
scraper NIE potrzebuje Playwrighta — wystarczy zwykły requests.get() +
regex na UUID, dużo taniej niż odpalanie przeglądarki co dzień.

Szuka wzorca UUID (8-4-4-4-12 hex) w statycznym HTML-u strony press
i drukuje kontekst wokół każdego trafienia.
"""
import re
import requests

URL = "https://www.biedronka.pl/pl/press,id,j0pu3be7s,title,codziennie-niskie-ceny-p-oferta-od-03-09"
UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}


def main():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    print(f"status={resp.status_code} bytes={len(resp.content)}")
    html = resp.text

    matches = list(UUID_PATTERN.finditer(html))
    print(f"\nUUID-podobnych trafień w statycznym HTML: {len(matches)}")
    for m in matches:
        start = max(0, m.start() - 200)
        print(f"\n-- UUID {m.group()} (offset {m.start()}) --")
        print(html[start:m.end() + 100])

    # Też: sam tag/element widgetu (żeby zobaczyć jak jest wywoływany)
    idx = html.find("leaflet-widget")
    print(f"\n\n'leaflet-widget' w HTML na offset: {idx}")
    if idx != -1:
        print(html[max(0, idx - 300):idx + 800])


if __name__ == "__main__":
    main()
