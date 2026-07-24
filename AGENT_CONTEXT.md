# AGENT_CONTEXT — CheapEat

> Plik dla AI asystenta (Perplexity). Aktualizuj po każdym zamkniętym epiku.
> Ostatnia aktualizacja: 2026-07-24

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
│   ├── schema.ts          # WatermelonDB appSchema (version: 1, 14 tabel)
│   └── index.ts
├── lib/
│   ├── supabase.ts        # Supabase client
│   ├── auth.ts            # Supabase Auth helpers
│   ├── sync.ts            # WatermelonDB ↔ Supabase sync
│   ├── onesignal.ts       # OneSignal init
│   └── sentry.ts          # Sentry init
├── model/
│   ├── database.ts        # Database instance (14 modeli zarejestrowanych)
│   ├── index.ts           # Re-export wszystkich modeli
│   ├── Store.ts
│   ├── Sklep.ts           # LEGACY — do usunięcia (duplikat Store.ts)
│   ├── StoreProduct.ts
│   ├── ProduktSklepu.ts   # LEGACY — do usunięcia (duplikat StoreProduct.ts)
│   ├── Price.ts
│   ├── Ingredient.ts
│   ├── IngredientMapping.ts
│   ├── Flyer.ts
│   ├── FlyerItem.ts
│   ├── Receipt.ts
│   ├── ReceiptItem.ts
│   ├── Recipe.ts
│   ├── RecipeIngredient.ts
│   ├── RecipeTag.ts
│   ├── UserIngredientPreference.ts
│   └── UserFavoriteRecipe.ts
├── services/
│   └── priceService.ts    # getCurrentPrice(storeProductId) — priorytet: paragon→gazetka→fallback
├── navigation/
└── screens/
```

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
| receipts | receipts |
| receipt_items | receipt_items |
| ingredient_mappings | ingredient_mappings |
| recipe_tags | recipe_tags |
| recipe_tag_relations | — (brak w WatermelonDB schema) |
| user_ingredient_preferences | user_ingredient_preferences |
| user_favorite_recipes | user_favorite_recipes |
| error_logs | — (tylko Supabase) |

> ⚠️ `recipe_tag_relations` i `error_logs` istnieją w Supabase ale NIE ma ich w WatermelonDB schema.ts — do uzgodnienia.

---

## Stan epików (Kanban)

### ✅ Zrobione
- Foundation (IDE, repo, Supabase config, ERD, modele danych, wybór stacku)
- Setup ADB + build/install loop na telefonie
- WatermelonDB rdzeń (schema v1, 14 modeli, database.ts)
- Połączenie RN ↔ Supabase (supabase.ts, sync.ts)
- Backend - Stores & Products (tabele: stores, store_products, prices + `priceService.ts`)

### 🔴 Do zrobienia (kolejność)
1. **Backend - Ingredients** — tabela ingredients już istnieje w Supabase i WatermelonDB; brakuje: seed danych (lista składników bazowych), logika normalizacji
2. **User Module** — tabela profiles w Supabase istnieje; brakuje: Supabase Auth flow w RN, tabele user_ingredient_preferences + user_favorite_recipes już istnieją
3. **Store Flyer Scraping** — brakuje: skrypty Python (Biedronka first), GitHub Actions cron, parser PDF/HTML
4. **Recipe Module** — tabele istnieją; brakuje: seed przepisów, scraper przepisów
5. **Product-Ingredient Mapping** — tabela ingredient_mappings istnieje; brakuje: panel admin UI + logika łączenia
6. **Shopping Cart Algorithm** — brakuje: cała logika (najdroższy epik)
7. **Receipt OCR** — brakuje: Google ML Kit, parser pozycji

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

- `Sklep.ts` i `ProduktSklepu.ts` w `src/model/` to duplikaty polskich nazw — nie są zarejestrowane w database.ts, do usunięcia
- Supabase projekt `cheapeat-dev` przechodzi w INACTIVE po okresie braku aktywności — przed pracą zawsze sprawdź status i przywróć jeśli trzeba
- Antigravity (lokalne IDE AI) ma bug z worktree przy uncommitted changes — używaj Perplexity → GitHub API jako głównego potoku kodu
