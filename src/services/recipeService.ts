import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { Recipe } from '../model/Recipe';
import { RecipeIngredient } from '../model/RecipeIngredient';
import { getIngredientMappings, packagesNeeded } from './ingredientService';
import { getCurrentPriceInfo } from './priceService';

// ---------------------------------------------------------------------------
// Pobieranie przepisów
// ---------------------------------------------------------------------------

/**
 * Zwraca wszystkie publiczne przepisy posortowane po tytule.
 */
export async function getPublicRecipes(): Promise<Recipe[]> {
  return database
    .get<Recipe>('recipes')
    .query(
      Q.where('is_public', true),
      Q.sortBy('title', Q.asc)
    )
    .fetch();
}

/**
 * Zwraca publiczne przepisy do Feedu — najnowsze pierwsze, opcjonalnie
 * przefiltrowane po tytule. Jedno źródło danych (lokalna baza) dla
 * wszystkich ekranów, żeby przepisy wyglądały i liczyły się tak samo
 * niezależnie od tego skąd pochodzą (scraper, seed, przyszłe źródła).
 */
export async function getFeedRecipes(searchQuery: string = ''): Promise<Recipe[]> {
  const clauses = [
    Q.where('is_public', true),
    Q.sortBy('updated_at', Q.desc),
  ];
  if (searchQuery.trim()) {
    clauses.unshift(Q.where('title', Q.like(`%${Q.sanitizeLikeString(searchQuery.trim())}%`)));
  }
  return database.get<Recipe>('recipes').query(...clauses).fetch();
}

/**
 * Zwraca przepis po ID.
 */
export async function getRecipeById(recipeId: string): Promise<Recipe | null> {
  try {
    return await database.get<Recipe>('recipes').find(recipeId);
  } catch {
    return null;
  }
}

/**
 * Zwraca składniki przepisu wraz z ilością i jednostką.
 */
export async function getRecipeIngredients(
  recipeId: string
): Promise<RecipeIngredient[]> {
  return database
    .get<RecipeIngredient>('recipe_ingredients')
    .query(Q.where('recipe_id', recipeId))
    .fetch();
}

// ---------------------------------------------------------------------------
// Kalkulacja kosztu przepisu
// ---------------------------------------------------------------------------

/** Jedna konkretna oferta sklepowa dla składnika przepisu. */
export type IngredientOffer = {
  storeProductId: string;
  storeId: string;
  storeName: string;
  productName: string;
  pricePerPackage: number;   // cena JEDNEGO opakowania
  unitAmount: number;        // gramatura/pojemność/liczba sztuk w opakowaniu
  packagesNeeded: number;    // ile opakowań trzeba kupić na ten przepis
  costPln: number;           // packagesNeeded * pricePerPackage
  isPromo: boolean;
  regularPricePln: number | null;
  promoEndsOn: string | null;
  upcoming: { grossPricePln: number; startsOn: string } | null;
};

export type IngredientCostLine = {
  ingredientId: string;
  ingredientName: string;
  amount: number;
  unit: string;
  costPln: number | null;    // koszt CAŁYCH opakowań potrzebnych do pokrycia amount (nie ułamek ceny) — null = brak ceny w bazie (albo przyprawa, patrz IGNORED_IN_COST)
  pricePerUnit: number | null; // cena JEDNEGO opakowania
  packagesNeeded: number | null; // ile opakowań trzeba kupić (costPln = packagesNeeded * pricePerUnit)
  unitAmount: number | null;     // gramatura/pojemność jednego opakowania
  storeName: string | null;  // sklep, w którym znaleziono tę opcję
  productName: string | null;
  isPromo: boolean;
  regularPricePln: number | null;
  promoEndsOn: string | null;
  /** Promocja jeszcze nieobowiązująca (gazetka "od czwartku"). */
  upcoming: { grossPricePln: number; startsOn: string } | null;
};

/**
 * Jeden sposób zrobienia zakupów na ten przepis.
 *
 * Apka pokazuje dwa naraz, bo to dwie różne odpowiedzi na to samo
 * pytanie "ile to kosztuje": najtaniej jak się da (skacząc między
 * sklepami) i najtaniej w JEDNYM sklepie (bo mało kto jedzie po masło do
 * drugiego marketu). Bez tej drugiej liczby "najtańszy koszyk" jest
 * mylący — sugeruje cenę, której w praktyce nikt nie zapłaci.
 */
export type ShoppingPlan = {
  kind: 'cheapest-basket' | 'single-store';
  /** Sklepy, do których trzeba wejść ("cheapest-basket" bywa wielosklepowy). */
  storeNames: string[];
  totalCostPln: number | null;
  costPerPortionPln: number | null;
  lines: IngredientCostLine[];
  missingPrices: string[];
};

export type RecipeCostResult = {
  recipeId: string;
  title: string;
  portions: number;
  /** Najtaniej jak się da — każdy składnik z najtańszego sklepu. */
  cheapestBasket: ShoppingPlan;
  /** Najtaniej w jednym sklepie; null, gdy żaden sklep nie wycenia niczego. */
  singleStore: ShoppingPlan | null;
  /** Ile się oszczędza, jeżdżąc po kilku sklepach zamiast do jednego. */
  multiStoreSavingsPln: number | null;

  // Skróty do "cheapestBasket" — starsze ekrany czytają je wprost.
  totalCostPln: number | null;
  costPerPortionPln: number | null;
  lines: IngredientCostLine[];
  missingPrices: string[];
};

// Przyprawy/dodatki, których koszt na porcję jest pomijalny i nie da się
// go sensownie policzyć z ceny całego opakowania (np. sól kupowana raz na
// pół roku) — nie wymagamy dla nich ceny i nie wliczamy ich do sumy.
// Eksportowane, żeby cartService.ts stosował tę samą regułę.
export const IGNORED_IN_COST = new Set(['sól']);

type IngredientRow = {
  ingredientId: string;
  ingredientName: string;
  amount: number;
  unit: string;
  ignored: boolean;
  offers: IngredientOffer[];
};

const emptyLine = (row: IngredientRow): IngredientCostLine => ({
  ingredientId: row.ingredientId,
  ingredientName: row.ingredientName,
  amount: row.amount,
  unit: row.unit,
  costPln: null,
  pricePerUnit: null,
  packagesNeeded: null,
  unitAmount: null,
  storeName: null,
  productName: null,
  isPromo: false,
  regularPricePln: null,
  promoEndsOn: null,
  upcoming: null,
});

const lineFromOffer = (row: IngredientRow, offer: IngredientOffer): IngredientCostLine => ({
  ...emptyLine(row),
  costPln: offer.costPln,
  pricePerUnit: offer.pricePerPackage,
  packagesNeeded: offer.packagesNeeded,
  unitAmount: offer.unitAmount,
  storeName: offer.storeName,
  productName: offer.productName,
  isPromo: offer.isPromo,
  regularPricePln: offer.regularPricePln,
  promoEndsOn: offer.promoEndsOn,
  upcoming: offer.upcoming,
});

/**
 * Zbiera WSZYSTKIE oferty na każdy składnik przepisu — po jednej na
 * zmapowany produkt sklepowy, z policzoną liczbą opakowań i kosztem.
 *
 * Koszt to CENA CAŁYCH OPAKOWAŃ, nie ułamek proporcjonalny do ilości w
 * przepisie: 30 g masła oznacza kupno całej kostki i zapłatę za całą
 * kostkę. Wyjątkiem są produkty na wagę, które scraper zapisuje jako
 * opakowanie 1 g — tam ta sama formuła wychodzi proporcjonalnie, bez
 * żadnego wyjątku w kodzie.
 */
async function collectOffers(recipeId: string): Promise<IngredientRow[]> {
  const recipeIngredients = await getRecipeIngredients(recipeId);
  const rows: IngredientRow[] = [];

  for (const ri of recipeIngredients) {
    const ingredientId = (ri as any).ingredientId as string;
    let ingredientName = ingredientId;
    try {
      const ingredient = await database.get('ingredients').find(ingredientId);
      ingredientName = (ingredient as any).name ?? ingredientId;
    } catch {}

    const amount = (ri as any).amount as number;
    const unit = (ri as any).unit as string;
    const row: IngredientRow = {
      ingredientId, ingredientName, amount, unit,
      ignored: IGNORED_IN_COST.has(ingredientName),
      offers: [],
    };
    rows.push(row);
    if (row.ignored) continue;

    for (const mapping of await getIngredientMappings(ingredientId)) {
      const storeProductId = (mapping as any).storeProductId as string;
      const info = await getCurrentPriceInfo(storeProductId);
      if (info === null) continue;

      let product: any;
      try {
        product = await database.get('store_products').find(storeProductId);
      } catch {
        continue;
      }

      // Wielkość i jednostka opakowania idą wprost z produktu sklepowego —
      // tylko tam wiadomo, czy to 200 g kostka czy 10 sztuk. Jeśli jednostki
      // się nie zgadzają (przepis w sztukach, opakowanie w gramach), nie ma
      // bezpiecznego przelicznika — pomijamy, zamiast zgadywać wagę sztuki.
      const unitAmount = product.unitAmount as number | undefined;
      const productUnit = product.unit as string | undefined;
      if (!unitAmount || unitAmount <= 0 || productUnit !== unit) continue;

      let storeName = '';
      try {
        const store = await database.get('stores').find(product.storeId as string);
        storeName = (store as any).name ?? '';
      } catch {}

      const pkgs = packagesNeeded(amount, unitAmount);
      row.offers.push({
        storeProductId,
        storeId: product.storeId as string,
        storeName,
        productName: product.name as string,
        pricePerPackage: info.grossPricePln,
        unitAmount,
        packagesNeeded: pkgs,
        costPln: pkgs * info.grossPricePln,
        isPromo: info.isPromo,
        regularPricePln: info.regularPricePln,
        promoEndsOn: info.isPromo ? info.validTo : null,
        upcoming: info.upcoming,
      });
    }
  }

  return rows;
}

const cheapest = (offers: IngredientOffer[]): IngredientOffer | null =>
  offers.reduce<IngredientOffer | null>(
    (best, o) => (best === null || o.costPln < best.costPln ? o : best),
    null
  );

function buildPlan(
  kind: ShoppingPlan['kind'],
  rows: IngredientRow[],
  pick: (row: IngredientRow) => IngredientOffer | null,
  portions: number
): ShoppingPlan {
  const lines: IngredientCostLine[] = [];
  const missingPrices: string[] = [];
  const storeNames = new Set<string>();
  let total = 0;
  let hasAnyCost = false;

  for (const row of rows) {
    if (row.ignored) {
      lines.push(emptyLine(row));
      continue;
    }
    const offer = pick(row);
    if (offer === null) {
      missingPrices.push(row.ingredientName);
      lines.push(emptyLine(row));
      continue;
    }
    hasAnyCost = true;
    total += offer.costPln;
    if (offer.storeName) storeNames.add(offer.storeName);
    lines.push(lineFromOffer(row, offer));
  }

  return {
    kind,
    storeNames: [...storeNames].sort(),
    totalCostPln: hasAnyCost ? Math.round(total * 100) / 100 : null,
    costPerPortionPln: hasAnyCost ? Math.round((total / portions) * 100) / 100 : null,
    lines,
    missingPrices,
  };
}

/**
 * Oblicza koszt przepisu na DWA sposoby, bo to dwie różne odpowiedzi:
 *
 * - `cheapestBasket` — każdy składnik z najtańszego sklepu, jaki go ma.
 *   Najniższa możliwa kwota, ale może wymagać objazdu kilku sklepów.
 * - `singleStore` — wszystko w jednym sklepie; wybieramy ten, który
 *   wycenia NAJWIĘCEJ składników, a przy remisie jest najtańszy. Sklep
 *   pokrywający pół listy nie jest lepszą opcją tylko dlatego, że jego
 *   niepełna suma wychodzi niżej.
 *
 * Zwraca sumę z tego, co udało się wycenić, nawet jeśli części
 * składników brakuje ceny — brakujące są wypisane w missingPrices,
 * żeby UI mogło pokazać "cena szacunkowa".
 */
export async function calculateRecipeCost(
  recipeId: string
): Promise<RecipeCostResult | null> {
  const recipe = await getRecipeById(recipeId);
  if (!recipe) return null;

  const rows = await collectOffers(recipeId);
  const portions = recipe.portions ?? 1;

  const cheapestBasket = buildPlan('cheapest-basket', rows, row => cheapest(row.offers), portions);

  const storeIds = [...new Set(rows.flatMap(r => r.offers.map(o => o.storeId)))];
  const perStore = storeIds
    .map(storeId =>
      buildPlan('single-store', rows,
        row => cheapest(row.offers.filter(o => o.storeId === storeId)), portions)
    )
    .filter(plan => plan.totalCostPln !== null);

  perStore.sort((a, b) =>
    a.missingPrices.length !== b.missingPrices.length
      ? a.missingPrices.length - b.missingPrices.length
      : (a.totalCostPln ?? Infinity) - (b.totalCostPln ?? Infinity)
  );
  const singleStore = perStore[0] ?? null;

  // Oszczędność liczymy tylko między planami o TAKIM SAMYM pokryciu —
  // inaczej "zaoszczędziłeś 12 zł" znaczyłoby w istocie "w tym sklepie
  // jednego składnika w ogóle nie ma".
  const comparable =
    singleStore !== null &&
    singleStore.missingPrices.length === cheapestBasket.missingPrices.length &&
    singleStore.totalCostPln !== null &&
    cheapestBasket.totalCostPln !== null;
  const multiStoreSavingsPln = comparable
    ? Math.round((singleStore!.totalCostPln! - cheapestBasket.totalCostPln!) * 100) / 100
    : null;

  return {
    recipeId,
    title: recipe.title,
    portions,
    cheapestBasket,
    singleStore,
    multiStoreSavingsPln,
    totalCostPln: cheapestBasket.totalCostPln,
    costPerPortionPln: cheapestBasket.costPerPortionPln,
    lines: cheapestBasket.lines,
    missingPrices: cheapestBasket.missingPrices,
  };
}

// ---------------------------------------------------------------------------
// Wyszukiwanie przepisów po składniku
// ---------------------------------------------------------------------------

/**
 * Zwraca przepisy zawierające dany składnik.
 */
export async function getRecipesByIngredient(
  ingredientId: string
): Promise<Recipe[]> {
  const recipeIngredients = await database
    .get<RecipeIngredient>('recipe_ingredients')
    .query(Q.where('ingredient_id', ingredientId))
    .fetch();

  const recipeIds = recipeIngredients.map(ri => (ri as any).recipeId as string);
  if (recipeIds.length === 0) return [];

  return database
    .get<Recipe>('recipes')
    .query(
      Q.where('id', Q.oneOf(recipeIds)),
      Q.where('is_public', true)
    )
    .fetch();
}

/**
 * Filtruje przepisy na podstawie preferencji użytkownika (wyklucza alergeny i dislike).
 */
export async function getRecipesForUser(
  excludedIngredientIds: string[]
): Promise<Recipe[]> {
  if (excludedIngredientIds.length === 0) {
    return getPublicRecipes();
  }

  // Znajdź ID przepisów z wykluczonymi składnikami
  const excluded = await database
    .get<RecipeIngredient>('recipe_ingredients')
    .query(Q.where('ingredient_id', Q.oneOf(excludedIngredientIds)))
    .fetch();

  const excludedRecipeIds = [...new Set(excluded.map(ri => (ri as any).recipeId as string))];

  return database
    .get<Recipe>('recipes')
    .query(
      Q.where('is_public', true),
      Q.where('id', Q.notIn(excludedRecipeIds)),
      Q.sortBy('title', Q.asc)
    )
    .fetch();
}
