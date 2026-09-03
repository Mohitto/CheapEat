"""
probe_biedronka_leaflet_api.py — jednorazowy skrypt diagnostyczny.

probe_biedronka_network.py (Playwright) znalazł prawdziwe REST API:
https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web
Zwraca JSON z "images_desktop" (lista PNG per strona gazetki). Ale
print(r.text[:2000]) uciął odpowiedź — trzeba sprawdzić PEŁNY JSON:
czy oprócz obrazków są też hotspoty/produkty/ceny jako osobne pole
(typowy wzorzec: obrazek strony + nakładka z klikalnymi cenami).

Sprawdza też endpoint listy gazetek (bez UUID), żeby ustalić jak
programowo znaleźć aktualny UUID zamiast go zgadywać/hardkodować.
"""
import json
import requests

LEAFLET_ID = "0f4c0a96-8ec9-4bb6-8dff-1d9adb0ef2d0"
LEAFLET_DETAIL_URL = f"https://leaflet-api.prod.biedronka.cloud/api/leaflets/{LEAFLET_ID}?ctx=web"

LIST_CANDIDATES = [
    "https://leaflet-api.prod.biedronka.cloud/api/leaflets?ctx=web",
    "https://leaflet-api.prod.biedronka.cloud/api/leaflets",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def probe(url: str) -> None:
    print(f"\n{'='*70}\n{url}\n{'='*70}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print(f"status={resp.status_code} content-type={resp.headers.get('content-type')} bytes={len(resp.content)}")
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    try:
        data = resp.json()
    except Exception as e:
        print(f"[NOT JSON] {e}")
        print(resp.text[:1000])
        return

    if isinstance(data, dict):
        print(f"Top-level klucze: {list(data.keys())}")
        for k, v in data.items():
            if k in ("images_desktop", "images_mobile"):
                print(f"  {k}: lista, {len(v)} elementów, przykład[0]={json.dumps(v[0])[:300] if v else None}")
            else:
                print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:500]}")
    elif isinstance(data, list):
        print(f"Lista, {len(data)} elementów")
        if data:
            print(f"przykład[0]: {json.dumps(data[0], ensure_ascii=False)[:1000]}")
            if len(data) > 1:
                print(f"przykład[1]: {json.dumps(data[1], ensure_ascii=False)[:1000]}")
    else:
        print(f"Nieoczekiwany typ: {type(data)}")


def main():
    probe(LEAFLET_DETAIL_URL)
    for url in LIST_CANDIDATES:
        probe(url)


if __name__ == "__main__":
    main()
