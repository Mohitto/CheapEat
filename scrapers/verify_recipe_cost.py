"""
verify_recipe_cost.py — podgląd przepisu bez telefonu.

Apka to czysty React Native CLI (bez Expo) — w tym środowisku (headless,
bez Android SDK/emulatora, bez Xcode) nie da się uruchomić UI i zobaczyć
przepisu "na żywo". Ten skrypt liczy koszt DOKŁADNIE tym samym
algorytmem co src/services/{recipeService,priceService,ingredientService}.ts,
ale bezpośrednio na Supabase, żeby potwierdzić, że liczby faktycznie
przepływają od zescrapowanej ceny do kosztu przepisu.

Odtworzona logika (do zsynchronizowania ręcznie, jeśli TS się zmieni):

- getCurrentPriceInfo (priceService.ts): cena promocyjna z gazetki
  obowiązująca DZISIAJ wygrywa; gdy jej nie ma albo wygasła — cena
  regularna. Ceny z gazetek jeszcze nieobowiązujących (Biedronka
  publikuje wydanie kilka dni przed startem) nie wchodzą do rachunku,
  ale pokazujemy je jako "od DD.MM".
- collectOffers + buildPlan (recipeService.ts): koszt CAŁYCH opakowań
  (packagesNeeded * cena opakowania), liczony osobno dla dwóch planów —
  "najtańsze zakupy" (każdy składnik z najtańszego sklepu) i "jeden
  sklep" (wszystko w jednym; wybieramy sklep z największym pokryciem, a
  przy remisie najtańszy).
- packagesNeeded (ingredientService.ts): ceil(amount / unit_amount).
  Produkt na wagę scraper zapisuje jako opakowanie 1 g, więc ta sama
  formuła wychodzi tam proporcjonalnie.
"""
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

from base_scraper import get_supabase

sb = get_supabase()

IGNORED_IN_COST = {"sól"}
PROMO_SOURCES = {"flyer-ocr", "flyer-ssr", "flyer"}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _short(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}"


def get_current_price_info(store_product_id: str) -> dict | None:
    rows = sb.table("prices").select("*").eq("store_product_id", store_product_id).execute().data
    if not rows:
        return None

    today = _today()

    def valid_now(r):
        if r.get("valid_from") and r["valid_from"] > today:
            return False
        if r.get("valid_to") and r["valid_to"] < today:
            return False
        return True

    def newest(rs):
        return sorted(rs, key=lambda r: r.get("updated_at") or r.get("created_at") or "")[-1] if rs else None

    regular = newest([r for r in rows if r["source"] not in PROMO_SOURCES and valid_now(r)])
    promo = newest([r for r in rows if r["source"] in PROMO_SOURCES and valid_now(r)])

    future = sorted(
        [r for r in rows if r["source"] in PROMO_SOURCES
         and r.get("valid_from") and r["valid_from"] > today],
        key=lambda r: r["valid_from"],
    )
    upcoming = ({"gross_price": future[0]["gross_price"], "starts_on": future[0]["valid_from"]}
                if future else None)

    if promo:
        regular_price = regular["gross_price"] if regular else None
        return {
            "gross_price": promo["gross_price"],
            "source": promo["source"],
            "is_promo": True,
            "regular_price": regular_price if regular_price and regular_price > promo["gross_price"] else None,
            "valid_to": promo.get("valid_to"),
            "upcoming": upcoming,
        }
    if regular:
        return {
            "gross_price": regular["gross_price"],
            "source": regular["source"],
            "is_promo": False,
            "regular_price": None,
            "valid_to": regular.get("valid_to"),
            "upcoming": upcoming,
        }
    return None


def collect_offers(recipe_id: str) -> list[dict]:
    rows = []
    for ri in sb.table("recipe_ingredients").select("*").eq("recipe_id", recipe_id).execute().data:
        ing = sb.table("ingredients").select("name").eq("id", ri["ingredient_id"]).execute().data
        name = ing[0]["name"] if ing else ri["ingredient_id"]
        row = {
            "ingredient_id": ri["ingredient_id"],
            "name": name,
            "amount": ri["amount"],
            "unit": ri["unit"],
            "ignored": name in IGNORED_IN_COST,
            "offers": [],
        }
        rows.append(row)
        if row["ignored"]:
            continue

        mappings = sb.table("ingredient_mappings").select("*") \
            .eq("ingredient_id", ri["ingredient_id"]).order("priority").execute().data
        for mapping in mappings:
            info = get_current_price_info(mapping["store_product_id"])
            if info is None:
                continue
            sp_res = sb.table("store_products").select("*, stores(id,name)") \
                .eq("id", mapping["store_product_id"]).execute().data
            if not sp_res:
                continue
            sp = sp_res[0]
            unit_amount = sp.get("unit_amount") or 0
            if unit_amount <= 0 or sp.get("unit") != ri["unit"]:
                continue

            packages = math.ceil(ri["amount"] / unit_amount)
            store = sp.get("stores") or {}
            row["offers"].append({
                **info,
                "store_id": store.get("id") or sp.get("store_id"),
                "store_name": store.get("name") or "?",
                "product_name": sp["name"],
                "unit_amount": unit_amount,
                "packages": packages,
                "cost": packages * info["gross_price"],
            })
    return rows


def build_plan(rows: list[dict], pick, portions: int) -> dict:
    lines, missing, stores = [], [], set()
    total, has_any = 0.0, False

    for row in rows:
        if row["ignored"]:
            lines.append({"row": row, "offer": None, "skipped": True})
            continue
        offer = pick(row)
        if offer is None:
            missing.append(row["name"])
            lines.append({"row": row, "offer": None, "skipped": False})
            continue
        has_any = True
        total += offer["cost"]
        stores.add(offer["store_name"])
        lines.append({"row": row, "offer": offer, "skipped": False})

    return {
        "stores": sorted(stores),
        "total": round(total, 2) if has_any else None,
        "per_portion": round(total / portions, 2) if has_any else None,
        "lines": lines,
        "missing": missing,
    }


def cheapest(offers):
    return min(offers, key=lambda o: o["cost"]) if offers else None


def print_plan(title: str, plan: dict) -> None:
    print(f"\n  {title}: ", end="")
    if plan["total"] is None:
        print("brak cen")
        return
    print(f"{plan['total']:.2f} zł · {plan['per_portion']:.2f} zł/porcję "
          f"[{' + '.join(plan['stores'])}]")

    for entry in plan["lines"]:
        row, offer = entry["row"], entry["offer"]
        label = f"{row['name']} ({row['amount']:g} {row['unit']})"
        if entry["skipped"]:
            print(f"    · {label}: pominięty (przyprawa)")
            continue
        if offer is None:
            print(f"    ✗ {label}: BRAK CENY")
            continue

        if offer["unit_amount"] == 1 and row["unit"] != "szt":
            what = f"{offer['packages']:g}{row['unit']} na wagę"
        else:
            what = f"kup {offer['packages']}x {offer['unit_amount']:g}{row['unit']}"
        extra = []
        if offer["is_promo"]:
            extra.append("PROMOCJA" + (f" do {_short(offer['valid_to'])}" if offer.get("valid_to") else ""))
        if offer.get("regular_price"):
            extra.append(f"regularnie {offer['regular_price'] * offer['packages']:.2f} zł")
        if offer.get("upcoming"):
            u = offer["upcoming"]
            extra.append(f"od {_short(u['starts_on'])}: {u['gross_price']:.2f} zł/opak.")
        print(f"    ✓ {label}: {offer['cost']:.2f} zł  "
              f"({what} @ {offer['gross_price']:.2f} zł, {offer['store_name']}, "
              f"{offer['source']})"
              + (f"\n        {' | '.join(extra)}" if extra else ""))
        print(f"        {offer['product_name']}")


def calculate_recipe_cost(recipe_title_like: str) -> None:
    recipe_res = sb.table("recipes").select("*").ilike("title", f"%{recipe_title_like}%").limit(1).execute()
    if not recipe_res.data:
        print(f"Nie znaleziono przepisu pasującego do '{recipe_title_like}'")
        return
    recipe = recipe_res.data[0]
    portions = recipe.get("portions") or 1
    print(f"\n=== {recipe['title']} ({portions} porcje) ===")

    rows = collect_offers(recipe["id"])

    basket = build_plan(rows, lambda r: cheapest(r["offers"]), portions)
    print_plan("NAJTAŃSZE ZAKUPY", basket)

    store_ids = {o["store_id"] for r in rows for o in r["offers"]}
    plans = [build_plan(rows, lambda r, sid=sid: cheapest([o for o in r["offers"] if o["store_id"] == sid]), portions)
             for sid in store_ids]
    plans = [p for p in plans if p["total"] is not None]
    plans.sort(key=lambda p: (len(p["missing"]), p["total"]))

    if plans:
        print_plan("JEDEN SKLEP", plans[0])
        if len(plans[0]["missing"]) == len(basket["missing"]):
            saved = round(plans[0]["total"] - basket["total"], 2)
            if saved > 0:
                print(f"\n  Objazd kilku sklepów oszczędza {saved:.2f} zł.")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["Naleśniki", "Omlet"]
    for t in targets:
        calculate_recipe_cost(t)
