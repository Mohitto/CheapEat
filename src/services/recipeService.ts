import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { Recipe } from '../model/Recipe';
import { RecipeIngredient } from '../model/RecipeIngredient';
import { getIngredientMappings, calculateIngredientCostPer100g } from './ingredientService';
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
  costPln: number | null;    // null = brak ceny w bazie
  pricePerUnit: number | null;
  storeName: string | null;  // sklep, w którym znaleziono najtańszą opcję
};

export type RecipeCostResult = {
  recipeId: string;
  title: string;
  portions: number;
  totalCostPln: number | null;        // null jeśli którykolwiek składnik bez ceny
  costPerPortionPln: number | null;
  lines: IngredientCostLine[];
  missingPrices: string[];            // nazwy składników bez ceny
};

/**
 * Oblicza szacowany koszt przepisu na podstawie aktualnych cen.
 * Dla każdego składnika:
 * 1. Znajduje mapowania produkt-składnik
 * 2. Pobiera aktualną cenę przez getCurrentPrice
 * 3. Przelicza koszt przez calculateIngredientCostPer100g
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
  let hasAllPrices = true;

  for (const ri of recipeIngredients) {
    const ingredientId = (ri as any).ingredientId as string;
    let ingredientName = ingredientId;

    try {
      const ingredient = await database.get('ingredients').find(ingredientId);
      ingredientName = (ingredient as any).name ?? ingredientId;
    } catch {}

    // Pobierz mapowania produkt -> składnik
    const mappings = await getIngredientMappings(ingredientId);
    const amount = (ri as any).amount as number;

    let costPln: number | null = null;
    let pricePerUnit: number | null = null;
    let storeName: string | null = null;

    // Sprawdź WSZYSTKIE mapowania i wybierz najtańszą opcję (nie pierwszą z brzegu)
    for (const mapping of mappings) {
      const storeProductId = (mapping as any).storeProductId as string;
      const price = await getCurrentPrice(storeProductId);
      if (price === null) continue;

      const conversionFactor = (mapping as any).conversionFactor ?? 1;
      const costPer100g = calculateIngredientCostPer100g(price, conversionFactor);
      const candidateCost = (costPer100g / 100) * amount;

      if (costPln === null || candidateCost < costPln) {
        costPln = candidateCost;
        pricePerUnit = price;
        try {
          const product = await database.get('store_products').find(storeProductId);
          const storeId = (product as any).storeId as string;
          const store = await database.get('stores').find(storeId);
          storeName = (store as any).name ?? null;
        } catch {
          storeName = null;
        }
      }
    }

    if (costPln === null) {
      hasAllPrices = false;
      missingPrices.push(ingredientName);
    } else {
      totalCost += costPln;
    }

    lines.push({
      ingredientId,
      ingredientName,
      amount,
      unit: (ri as any).unit,
      costPln,
      pricePerUnit,
      storeName,
    });
  }

  const portions = recipe.portions ?? 1;

  return {
    recipeId,
    title: recipe.title,
    portions,
    totalCostPln: hasAllPrices ? Math.round(totalCost * 100) / 100 : null,
    costPerPortionPln: hasAllPrices ? Math.round((totalCost / portions) * 100) / 100 : null,
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
