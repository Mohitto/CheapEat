# AGENT_CONTEXT — CheapEat

> Plik dla AI asystenta. Aktualizuj po każdym zamkniętym epiku.
> Ostatnia aktualizacja: 2026-08-20

---

## Rdzeń produktu

CheapEat zestawia przepisy z internetu (na start: aniagotuje.pl) z aktualnymi
gazetkami promocyjnymi (na start: Biedronka, docelowo też Lidl) i pokazuje,
ile realnie wyjdą zakupy na dany przepis — czyli **najtańsze przepisy w
oparciu o ceny z gazetek**. To jedyny główny loop aplikacji; funkcja
paragonów/OCR (skanowanie paragonu) została świadomie porzucona — cały
związany z nią kod, model danych i uprawnienia zostały usunięte.

---

## Stack

| Warstwa | Technologia |
|---|---|
| Mobile | React Native (TypeScript) |
| Lokalna baza | WatermelonDB (SQLite) |
| Zdalna baza | Supabase (PostgreSQL) — `ncksaaafqovbrvjetlcc` (`cheapeat-dev`, `eu-west-1`) |
| Auth | Supabase Auth (anonimowy login) |
| Powiadomienia | OneSignal |
| Monitoring | Sentry |
| Repo | https://github.com/Mohitto/CheapEat.git (branch: `main`) |

---

## Struktura src/

```
src/
├── db/
│   ├── schema.ts          # WatermelonDB appSchema (version: 4, bez receipts/receipt_items)
│   └── migrations.ts
├── lib/
│   ├── supabase.ts        # Supabase client
│   ├── auth.ts            # Supabase Auth helpers (ensureSession — anonimowy login)
│   ├── sync.ts            # WatermelonDB ↔ Supabase sync
│   ├── onesignal.ts       # OneSignal init — NIEUŻYWANE, pakiet nie zainstalowany, @ts-nocheck
│   └── sentry.ts          # Sentry init — NIEUŻYWANE, pakiet nie zainstalowany, @ts-nocheck
├── model/
│   ├── database.ts        # Database instance (12 modeli zarejestrowanych)
│   ├── index.ts           # Re-export wszystkich modeli
│   ├── Store.ts / StoreProduct.ts / Price.ts
│   ├── Ingredient.ts / IngredientMapping.ts
│   ├── Flyer.ts / FlyerItem.ts
│   ├── Recipe.ts / RecipeIngredient.ts / RecipeTag.ts
│   └── UserIngredientPreference.ts / UserFavoriteRecipe.ts
├── services/
│   ├── priceService.ts     # getCurrentPrice(storeProductId) — priorytet: gazetka→fallback
│   ├── ingredientService.ts# normalizacja nazw, dopasowanie produkt→składnik
│   ├── mappingService.ts   # ingredient_mappings (auto-map + admin RPC)
│   ├── recipeService.ts    # pobieranie przepisów + calculateRecipeCost (koszt przepisu)
│   ├── cartService.ts      # buildCartForRecipes — koszyk wielu przepisów, porównanie sklepów
│   └── userService.ts      # profil, preferencje składników, ulubione przepisy
├── navigation/              # RootNavigator (stack) + BottomTabNavigator (Feed/Cart/Preferences)
└── screens/                 # FeedScreen, RecipeDetailScreen, CartScreen, PreferencesScreen
```

App.tsx przy starcie woła `ensureSession()` (anonimowe logowanie Supabase)
i `syncDatabase()` (pierwszy pull danych do WatermelonDB) zanim pokaże
nawigację — bez tego lokalna baza jest pusta i `RecipeDetailScreen`/
`CartScreen` (liczące koszt przepisu) nic by nie znalazły.

---

## Supabase — tabele (public schema, wszystkie z RLS)

| Tabela | Odpowiednik WatermelonDB |
|---|---|
| profiles | — (brak w WatermelonDB) |
| stores | stores |
| ingredients | ingredients |
| recipes | recipes |
| recipe_ingredients | recipe_ingredients |
| store_products | store_products |
| prices | prices |
| flyers | flyers |
| flyer_items | flyer_items |
| ingredient_mappings | ingredient_mappings |
| recipe_tags | recipe_tags |
| recipe_tag_relations | — (brak w WatermelonDB schema) |
| user_ingredient_preferences | user_ingredient_preferences |
| user_favorite_recipes | user_favorite_recipes |
| error_logs | — (tylko Supabase) |

> ⚠️ `recipe_tag_relations` i `error_logs` istnieją w Supabase ale NIE ma ich w WatermelonDB schema.ts — do uzgodnienia.
> ⚠️ Tabele `receipts`/`receipt_items` w Supabase NIE są już używane przez aplikację
> (funkcja paragonów porzucona) — wciąż tam fizycznie istnieją, do usunięcia osobną migracją SQL, gdy ktoś się tym zajmie.

---

## Stan epików (Kanban)

### ✅ Zrobione
- Foundation (IDE, repo, Supabase config, ERD, modele danych, wybór stacku)
- Setup ADB + build/install loop na telefonie
- WatermelonDB rdzeń (schema v4, 12 modeli, database.ts)
- Połączenie RN ↔ Supabase (supabase.ts, sync.ts) + bootstrap sesji/sync w App.tsx
- Backend - Stores & Products (tabele: stores, store_products, prices + `priceService.ts`)
- Recipe Module — `recipeService.ts` (getRecipeById, calculateRecipeCost), FeedScreen czyta przepisy z Supabase (scraper aniagotuje.pl przez Edge Function), RecipeDetailScreen pokazuje koszt
- Shopping Cart Algorithm — `cartService.ts` (buildCartForRecipes, porównanie sklepów, najtańszy sklep), CartScreen
- Product-Ingredient Mapping — `mappingService.ts` + `ingredientService.ts` (normalizacja nazw, auto-map, RPC admin_upsert_mapping)
- User Module (częściowo) — anonimowe logowanie (`ensureSession`), preferencje składników + ulubione przepisy (`userService.ts`, `PreferencesScreen`)
- ~~Receipt OCR~~ — **porzucone**: cały kod (ReceiptScreen, receiptService, model Receipt/ReceiptItem, tabele lokalne, uprawnienia kamery) usunięty. Aplikacja skupia się wyłącznie na: przepisy + ceny z gazetek + koszt zakupów.

### 🔴 Do zrobienia (kolejność)
1. **Dane** — realne zasilenie: seed składników bazowych, mapowania produkt→składnik dla tego co scrapuje Biedronka, przepisy z aniagotuje.pl z realnymi recipe_ingredients (bez tego kalkulacja kosztu zawsze pokaże "brak cen")
2. **Store Flyer Scraping — Lidl** — Biedronka ma szkielet scrapera (`scrapers/biedronka/scraper.py`, endpoint do zweryfikowania), Lidl nie istnieje jeszcze wcale
3. **Lista przepisów z ceną na liście (Feed)** — obecnie cena/koszt liczy się dopiero po wejściu w szczegóły przepisu; do rozważenia pokazywanie szacunkowego kosztu już na karcie w Feedzie
4. **Admin UI do mapowania** — na razie tylko auto-map przez normalizację nazw + RPC, brak panelu do ręcznej korekty błędnych dopasowań

---

## Zasady pracy AI → GitHub

- Tworzę/modyfikuję pliki przez GitHub API (`create_or_update_file`, `push_files`)
- Przed modyfikacją istniejącego pliku zawsze pobieram aktualny SHA
- Po każdej zmianie podaję link do commita
- Migracje SQL wykonuję przez Supabase MCP (`apply_migration`), nie ręcznie
- Nie commituj do branchy innych niż `main` bez wyraźnej prośby
- Po każdym zamkniętym epiku aktualizuj ten plik

---

## Znane problemy / dług techniczny

- Supabase projekt `cheapeat-dev` przechodzi w INACTIVE po okresie braku aktywności — przed pracą zawsze sprawdź status i przywróć jeśli trzeba
- `onesignal.ts`/`sentry.ts` — pakiety JS nie są zainstalowane, moduły oznaczone `@ts-nocheck` i nie wpięte do App.tsx; do świadomego podłączenia gdy będzie realny DSN/App ID
- Tabele `receipts`/`receipt_items` w Supabase to relikt po porzuconej funkcji paragonów — do usunięcia osobną migracją SQL
