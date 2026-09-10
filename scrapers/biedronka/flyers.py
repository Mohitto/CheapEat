"""
flyers.py — odkrywanie gazetek Biedronki i ich okresów obowiązywania.

Wcześniej scraper brał JEDNĄ gazetkę, wybraną po nazwie ("codziennie
-niskie-ceny"), i nadawał cenom sztywną ważność "dziś + 3 dni". To dawało
dwa realne błędy:

1. Biedronka publikuje kilkanaście gazetek naraz, w tym te, które
   ZACZYNAJĄ obowiązywać dopiero za kilka dni. Wybór po nazwie trafiał w
   gazetkę "oferta-od-10-09" 9 września — czyli w ceny, które jeszcze nie
   obowiązują.
2. Promocje tematyczne ("festiwal nabiału", "festiwal wędlin") mają
   własne gazetki, więc masło w promocji było niewidoczne, bo siedziało
   poza tą jedną gazetką, którą czytaliśmy.

Data startu jest w slugu adresu (…-oferta-od-10-09, …-od-9-09,
…-05-09#page=1). Daty końca Biedronka nie podaje — przyjmujemy dzień
przed startem następnej gazetki tego samego typu, a gdy takiej nie ma,
DEFAULT_DURATION_DAYS. Dzięki temu cena promocyjna sama wygasa, a apka
wraca do ceny regularnej ze sklepu.
"""
import re
from datetime import date, datetime, timedelta

import requests

GAZETKI_URL = "https://www.biedronka.pl/pl/gazetki"
PRESS_LINK_PATTERN = re.compile(
    r'href=["\'](?:https://www\.biedronka\.pl)?(/pl/press,id,[^"\'#]+)'
)
# "…-oferta-od-10-09", "…-od-9-09", "…-hity-i-inspiracje-05-09"
START_DATE_PATTERN = re.compile(r'(?:od|[a-z])-(\d{1,2})-(\d{1,2})(?:$|[^0-9])')

DEFAULT_DURATION_DAYS = 7
# Gazetki starsze niż to nie interesują nas nawet jako "poprzednie" —
# tylko zaśmiecałyby bazę wygasłymi cenami.
MAX_AGE_DAYS = 30
# Biedronka publikuje gazetkę na kilka dni przed startem ("OD CZWARTKU").
# Czytamy ją od razu, ale zapisujemy z jej PRAWDZIWĄ datą startu, więc
# apka pokaże te ceny dopiero, gdy zaczną obowiązywać. Bez tego główna,
# 96-stronicowa gazetka była 9 września w ogóle nieotwierana — a to w
# niej siedzi większość promocji.
LOOKAHEAD_DAYS = 10


def _parse_start_date(slug: str, today: date) -> date | None:
    """Data rozpoczęcia z sluga. Rok nie występuje w adresie, więc
    zakładamy bieżący; jeśli wypada to ponad miesiąc w przyszłość,
    to znaczy że chodzi o poprzedni rok (gazetka z grudnia oglądana
    w styczniu)."""
    matches = START_DATE_PATTERN.findall(slug)
    if not matches:
        return None
    day, month = matches[-1]
    try:
        parsed = date(today.year, int(month), int(day))
    except ValueError:
        return None
    if (parsed - today).days > 31:
        try:
            parsed = date(today.year - 1, int(month), int(day))
        except ValueError:
            return None
    return parsed


def _family(slug: str) -> str:
    """Nazwa cyklu gazetki bez daty wydania — "codziennie-niskie-ceny-p
    -oferta-od-10-09" i "…-od-07-09" to ta sama gazetka w dwóch
    wydaniach, więc nowsze wydanie kończy ważność starszego."""
    return re.sub(r'-?(?:oferta-)?(?:od-)?\d{1,2}-\d{1,2}.*$', '', slug)


def discover_flyers(today: date | None = None) -> list[dict]:
    """Wszystkie gazetki ogłoszone na /pl/gazetki, z policzonym okresem
    obowiązywania. Zwraca listę {path, slug, valid_from, valid_to},
    posortowaną od najnowszej."""
    today = today or datetime.now().date()

    resp = requests.get(GAZETKI_URL, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    })
    resp.raise_for_status()

    seen: set[str] = set()
    flyers: list[dict] = []
    for m in PRESS_LINK_PATTERN.finditer(resp.text):
        path = m.group(1)
        if path in seen:
            continue
        seen.add(path)

        start = _parse_start_date(path, today)
        if start is None or (today - start).days > MAX_AGE_DAYS:
            continue

        flyers.append({"path": path, "slug": path.split("title,")[-1], "valid_from": start})

    flyers.sort(key=lambda f: f["valid_from"], reverse=True)

    # Koniec obowiązywania: dzień przed startem kolejnej edycji tej samej
    # gazetki (kolejne wydania zastępują poprzednie), inaczej +7 dni.
    for i, f in enumerate(flyers):
        family = _family(f["slug"])
        successor = next(
            (o for o in flyers[:i]
             if _family(o["slug"]) == family and o["valid_from"] > f["valid_from"]),
            None,
        )
        if successor:
            f["valid_to"] = successor["valid_from"] - timedelta(days=1)
        else:
            f["valid_to"] = f["valid_from"] + timedelta(days=DEFAULT_DURATION_DAYS)

    return flyers


def active_flyers(today: date | None = None) -> list[dict]:
    """Gazetki obowiązujące DZISIAJ — te, których ceny wolno pokazywać
    jako dzisiejszą cenę."""
    today = today or datetime.now().date()
    return [f for f in discover_flyers(today)
            if f["valid_from"] <= today <= f["valid_to"]]


def scrapable_flyers(today: date | None = None) -> list[dict]:
    """Gazetki, które warto DZISIAJ przeczytać: obowiązujące teraz oraz
    już opublikowane, a startujące w ciągu najbliższych LOOKAHEAD_DAYS.

    Rozdział "czytamy" od "pokazujemy" jest tu celowy. Wcześniej scraper
    otwierał wyłącznie gazetki obowiązujące dzisiaj, więc wydanie
    ogłoszone jako "OD CZWARTKU" (a leżące na stronie już we wtorek)
    było pomijane w całości — razem z promocjami z jego pierwszej strony.
    Teraz czytamy je od razu, ale każda cena dostaje PRAWDZIWĄ datę
    startu, a priceService pokazuje ją dopiero, gdy zacznie obowiązywać.

    Każda pozycja dostaje `is_upcoming` — dzięki temu apka może napisać
    "od 10.09 taniej", zamiast udawać, że to cena na dziś."""
    today = today or datetime.now().date()
    horizon = today + timedelta(days=LOOKAHEAD_DAYS)
    out = []
    for f in discover_flyers(today):
        if f["valid_to"] < today or f["valid_from"] > horizon:
            continue
        out.append({**f, "is_upcoming": f["valid_from"] > today})
    return out
