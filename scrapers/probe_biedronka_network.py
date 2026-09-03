"""
probe_biedronka_network.py — jednorazowy skrypt diagnostyczny.

probe_endpoints.py ustalił, że statyczny HTML gazetki Biedronki
(press,id,...) NIE zawiera danych produktowych (cen, nazw) — jest tylko
konfiguracja (window.customPapers) mapująca ID sklepu na wariant gazetki.
Sam viewer stron używa createjs (canvas), co silnie sugeruje, że
prawdziwe dane strony (obrazek i/lub hotspoty z cenami) są dociągane
przez JS PO załadowaniu strony — czyli niewidoczne dla zwykłego requests.get().

Ten skrypt używa Playwright (nagłówkowa Chromia, już zainstalowana w tym
środowisku CI) żeby faktycznie odpalić stronę i podsłuchać WSZYSTKIE
requesty sieciowe, które robi w trakcie ładowania — to jedyny pewny
sposób na znalezienie prawdziwego manifestu/API flipbooka bez zgadywania.

Output na stdout — URL + fragment treści każdej odpowiedzi, która wygląda
na dane (json, xml, lub duży tekstowy payload), plus lista wszystkich
załadowanych obrazków (to strony gazetki jako bitmapy, jeśli nic innego
się nie znajdzie).
"""
from playwright.sync_api import sync_playwright

URL = "https://www.biedronka.pl/pl/press,id,j0pu3be7s,title,codziennie-niskie-ceny-p-oferta-od-03-09"

INTERESTING_EXT = (".json", ".xml", ".txt")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")


def main():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def on_response(response):
            try:
                url = response.url
                ctype = response.headers.get("content-type", "")
                captured.append((url, ctype, response.status))
            except Exception as e:
                print(f"[response handler error] {e}")

        page.on("response", on_response)

        print(f"Nawiguję do {URL} ...")
        page.goto(URL, wait_until="networkidle", timeout=45000)
        # Poczekaj chwilę na ewentualne opóźnione fetch'e po networkidle
        page.wait_for_timeout(3000)

        print(f"\nZłapano {len(captured)} response'ów.\n")

        json_like = [c for c in captured if "json" in c[1].lower() or c[0].lower().endswith(INTERESTING_EXT)]
        images = [c for c in captured if c[0].lower().split("?")[0].endswith(IMAGE_EXT)]
        others = [c for c in captured if c not in json_like and c not in images]

        print(f"{'='*70}\nJSON/XML/TXT responses: {len(json_like)}\n{'='*70}")
        for url, ctype, status in json_like:
            print(f"  [{status}] {ctype} {url}")

        print(f"\n{'='*70}\nObrazki: {len(images)}\n{'='*70}")
        for url, ctype, status in images:
            print(f"  [{status}] {url}")

        print(f"\n{'='*70}\nInne (JS, CSS, fonty, itp.) — pierwsze 60: {len(others)}\n{'='*70}")
        for url, ctype, status in others[:60]:
            print(f"  [{status}] {ctype} {url}")

        # Dla każdego JSON-podobnego, spróbuj pobrać treść (osobny request,
        # bo response.body() w trakcie handlera bywa zawodne przy dużym ruchu)
        print(f"\n{'='*70}\nPróba pobrania treści JSON/XML/TXT response'ów\n{'='*70}")
        import requests as req_lib
        for url, ctype, status in json_like[:15]:
            try:
                r = req_lib.get(url, timeout=15)
                print(f"\n-- {url} --")
                print(r.text[:2000])
            except Exception as e:
                print(f"  [fetch error] {url}: {e}")

        browser.close()


if __name__ == "__main__":
    main()
