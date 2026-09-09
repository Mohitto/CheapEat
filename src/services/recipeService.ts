import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { Recipe } from '../model/Recipe';
import { RecipeIngredient } from '../model/RecipeIngredient';
import { getIngredientMappings, packagesNeeded } from './ingredientService';
import { getCurrentPrice } from './priceService';

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

export type IngredientCostLine = {
  ingredientId: string;
  ingredientName: string;
  amount: number;
  unit: string;
  costPln: number | null;    // koszt CAŁYCH opakowań potrzebnych do pokrycia amount (nie ułamek ceny) — null = brak ceny w bazie (albo przyprawa, patrz IGNORED_IN_COST)
  pricePerUnit: number | null; // cena JEDNEGO opakowania
  packagesNeeded: number | null; // ile opakowań trzeba kupić (costPln = packagesNeeded * pricePerUnit)
  unitAmount: number | null;     // gramatura/pojemność jednego opakowania
  storeName: string | null;  // sklep, w którym znaleziono najtańszą opcję
};

export type RecipeCostResult = {
  recipeId: string;
  title: string;
  portions: number;
  totalCostPln: number | null;        // suma z tego co udało się wycenić; null tylko gdy NIC nie ma ceny
  costPerPortionPln: number | null;
  lines: IngredientCostLine[];
  missingPrices: string[];            // nazwy składników bez ceny (bez przypraw z IGNORED_IN_COST)
};

// Przyprawy/dodatki, których koszt na porcję jest pomijalny i nie da się
// go sensownie policzyć z ceny całego opakowania (np. sól kupowana raz na
// pół roku) — nie wymagamy dla nich ceny i nie wliczamy ich do sumy.
// Eksportowane, żeby cartService.ts stosował tę samą regułę.
export const IGNORED_IN_COST = new Set(['sól']);

/**
 * Oblicza szacowany koszt przepisu na podstawie aktualnych cen.
 * Dla każdego składnika (poza przyprawami z IGNORED_IN_COST):
 * 1. Znajduje mapowania produkt-składnik
 * 2. Pobiera aktualną cenę CAŁEGO opakowania przez getCurrentPrice
 * 3. Liczy ile opakowań trzeba kupić (packagesNeeded) i mnoży przez cenę
 *
 * Koszt to CENA CAŁYCH OPAKOWAŃ, nie ułamek proporcjonalny do ilości w
 * przepisie — składników nie da się kupić "na wagę dokładnie tyle ile
 * potrzeba" (potrzeba 30g masła -> kupujesz całą kostkę 200g, płacisz
 * za całą kostkę). Ta sama zasada co w cartService.ts (koszyk zakupów).
 *
 * Zwraca sumę z tego, co udało się wycenić, nawet jeśli części
 * składników brakuje ceny — brakujące są wypisane w missingPrices,
 * żeby UI mogło pokazać "cena szacunkowa", ale liczba i tak się pojawia
 * (usera bardziej interesuje orientacyjny koszt niż brak liczby).
 */
export async function calculateRecipeCost(
  recipeId: string
): Promise<RecipeCostResult | null> {
  const recipe = await getRecipeById(recipeId);
  if (!recipe) return null;

  const recipeIngredients = await getRecipeIngredients(recipeId);
  const lines: IngredientCostLine[] = [];
  const missingPrices: string[] = [];
  let totalCost = 0;
  let hasAnyCost = false;

  for (const ri of recipeIngredients) {
    const ingredientId = (ri as any).ingredientId as string;
    let ingredientName = ingredientId;

    try {
      const ingredient = await database.get('ingredients').find(ingredientId);
      ingredientName = (ingredient as any).name ?? ingredientId;
    } catch {}

    const amount = (ri as any).amount as number;
    const unit = (ri as any).unit;

    if (IGNORED_IN_COST.has(ingredientName)) {
      lines.push({
        ingredientId, ingredientName, amount, unit,
        costPln: null, pricePerUnit: null, packagesNeeded: null, unitAmount: null, storeName: null,
      });
      continue;
    }

    // Pobierz mapowania produkt -> składnik
    const mappings = await getIngredientMappings(ingredientId);

    let costPln: number | null = null;
    let pricePerUnit: number | null = null;
    let bestPackagesNeeded: number | null = null;
    let bestUnitAmount: number | null = null;
    let storeName: string | null = null;

    // Sprawdź WSZYSTKIE mapowania i wybierz opcję z najniższym kosztem
    // CAŁYCH opakowań potrzebnych do pokrycia tego przepisu (nie pierwszą
    // z brzegu, i nie tę z najniższą ceną za 100g — mały słoiczek droższy
    // per gram, ale wystarczający w jednym opakowaniu, może wyjść taniej
    // niż duże opakowanie tańsze per gram).
    for (const mapping of mappings) {
      const storeProductId = (mapping as any).storeProductId as string;
      const price = await getCurrentPrice(storeProductId);
      if (price === null) continue;

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

      const pkgs = packagesNeeded(amount, unitAmount);
      const candidateCost = pkgs * price;

      if (costPln === null || candidateCost < costPln) {
        costPln = candidateCost;
        pricePerUnit = price;
        bestPackagesNeeded = pkgs;
        bestUnitAmount = unitAmount;
        try {
          const store = await database.get('stores').find(product.storeId as string);
          storeName = (store as any).name ?? null;
        } catch {
          storeName = null;
        }
      }
    }

    if (costPln === null) {
      missingPrices.push(ingredientName);
    } else {
      hasAnyCost = true;
      totalCost += costPln;
    }

    lines.push({
      ingredientId, ingredientName, amount, unit,
      costPln, pricePerUnit, packagesNeeded: bestPackagesNeeded, unitAmount: bestUnitAmount, storeName,
    });
  }

  const portions = recipe.portions ?? 1;

  return {
    recipeId,
    title: recipe.title,
    portions,
    totalCostPln: hasAnyCost ? Math.round(totalCost * 100) / 100 : null,
    costPerPortionPln: hasAnyCost ? Math.round((totalCost / portions) * 100) / 100 : null,
    lines,
    missingPrices,
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
