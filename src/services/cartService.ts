/**
 * cartService.ts — Shopping Cart Algorithm
 *
 * Główne funkcje:
 * 1. buildCartForRecipes()  — dla listy przepisów generuje listę zakupów
 * 2. findCheapestStore()    — porównuje sklepy i wskazuje najtańszy
 * 3. mergeIngredients()     — scala zduplikowane składniki (kilka przepisów -> 1 lista)
 * 4. optimizeCart()         — zamienia składniki na najtańsze dostępne produkty
 */
import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { getRecipeIngredients } from './recipeService';
import { getMappingsByIngredient } from './mappingService';
import { getCurrentPrice } from './priceService';

// ---------------------------------------------------------------------------
// Typy
// ---------------------------------------------------------------------------

export type CartIngredientLine = {
  ingredientId: string;
  ingredientName: string;
  totalAmount: number;
  unit: string;
  /** Najlepszy produkt dla tego składnika */
  bestProduct: CartProductOption | null;
  /** Wszystkie opcje posortowane ceną */
  options: CartProductOption[];
};

export type CartProductOption = {
  storeProductId: string;
  productName: string;
  storeId: string;
  storeName: string;
  pricePerUnit: number;     // cena całego opakowania
  pricePerGram: number;     // cena / gram — do porównania jednostkowego
  unitAmount: number;       // gramatura opakowania
  totalCostPln: number;     // koszt pokrycia zapotrzebowania
  packagesNeeded: number;   // ile opakowań kupić
};

export type StoreCartSummary = {
  storeId: string;
  storeName: string;
  totalCostPln: number;
  coveragePercent: number;  // % składników dostępnych w tym sklepie
  missingIngredients: string[];
};

export type CartResult = {
  lines: CartIngredientLine[];
  storeSummaries: StoreCartSummary[];
  cheapestStoreId: string | null;
  cheapestStoreName: string | null;
  totalCostPln: number | null;
  missingPrices: string[];
};

// ---------------------------------------------------------------------------
// Pomocnicze
// ---------------------------------------------------------------------------

type RawIngredientNeed = {
  ingredientId: string;
  amount: number;
  unit: string;
};

/**
 * Scala zapotrzebowanie na te same składniki z wielu przepisów.
 * Zakłada, że wszystkie ilości są w gramach/ml (WatermelonDB konwencja).
 */
function mergeIngredientNeeds(
  needs: RawIngredientNeed[]
): Map<string, RawIngredientNeed> {
  const merged = new Map<string, RawIngredientNeed>();
  for (const need of needs) {
    const existing = merged.get(need.ingredientId);
    if (existing && existing.unit === need.unit) {
      existing.amount += need.amount;
    } else {
      merged.set(need.ingredientId, { ...need });
    }
  }
  return merged;
}

/**
 * Oblicza ile opakowań (packagesNeeded) trzeba kupić,
 * żeby pokryć zapotrzebowanie.
 */
function packagesNeeded(neededGrams: number, unitAmount: number): number {
  if (unitAmount <= 0) return 1;
  return Math.ceil(neededGrams / unitAmount);
}

// ---------------------------------------------------------------------------
// Główny algorytm
// ---------------------------------------------------------------------------

/**
 * Buduje koszyk dla podanej listy przepisów i liczby porcji.
 *
 * Algorytm:
 * 1. Zbierz składniki ze wszystkich przepisów
 * 2. Scal zduplikowane składniki (sumuj ilości)
 * 3. Dla każdego składnika pobierz mapowania -> produkty -> ceny
 * 4. Posortuj opcje ceną/gram (najtańsze pierwsze)
 * 5. Wylicz podsumowanie per sklep
 * 6. Wskaż najtańszy sklep
 */
export async function buildCartForRecipes(
  recipePortions: Array<{ recipeId: string; portions: number }>
): Promise<CartResult> {
  // 1. Zbierz surowe zapotrzebowanie
  const rawNeeds: RawIngredientNeed[] = [];

  for (const { recipeId, portions } of recipePortions) {
    const recipeIngredients = await getRecipeIngredients(recipeId);
    for (const ri of recipeIngredients) {
      rawNeeds.push({
        ingredientId: (ri as any).ingredientId as string,
        amount:       ((ri as any).amount as number) * portions,
        unit:         (ri as any).unit as string,
      });
    }
  }

  // 2. Scal
  const mergedNeeds = mergeIngredientNeeds(rawNeeds);

  // 3. Rozwiń do CartIngredientLine[]
  const lines: CartIngredientLine[] = [];
  const missingPrices: string[] = [];

  for (const [ingredientId, need] of mergedNeeds) {
    // Pobierz nazwę składnika
    let ingredientName = ingredientId;
    try {
      const ing = await database.get('ingredients').find(ingredientId);
      ingredientName = (ing as any).name ?? ingredientId;
    } catch {}

    // Pobierz mapowania (posortowane priorytetem)
    const mappings = await getMappingsByIngredient(ingredientId);

    const options: CartProductOption[] = [];

    for (const mapping of mappings) {
      const storeProductId    = (mapping as any).storeProductId as string;
      const conversionFactor  = (mapping as any).conversionFactor as number ?? 1.0;
      const unitAmount        = conversionFactor * 100; // gramatura opakowania

      const pricePerUnit = await getCurrentPrice(storeProductId);
      if (pricePerUnit === null) continue;

      // Pobierz dane produktu i sklepu
      let productName = storeProductId;
      let storeId     = '';
      let storeName   = '';
      try {
        const prod = await database.get('store_products').find(storeProductId);
        productName = (prod as any).name ?? storeProductId;
        storeId     = (prod as any).storeId as string;

        const store = await database.get('stores').find(storeId);
        storeName = (store as any).name ?? storeId;
      } catch {}

      const pricePerGram  = unitAmount > 0 ? pricePerUnit / unitAmount : pricePerUnit;
      const pkgs          = packagesNeeded(need.amount, unitAmount);
      const totalCostPln  = Math.round(pkgs * pricePerUnit * 100) / 100;

      options.push({
        storeProductId,
        productName,
        storeId,
        storeName,
        pricePerUnit,
        pricePerGram: Math.round(pricePerGram * 10000) / 10000,
        unitAmount,
        totalCostPln,
        packagesNeeded: pkgs,
      });
    }

    // Sortuj najtańsze/gram pierwsze
    options.sort((a, b) => a.pricePerGram - b.pricePerGram);

    if (options.length === 0) {
      missingPrices.push(ingredientName);
    }

    lines.push({
      ingredientId,
      ingredientName,
      totalAmount: need.amount,
      unit:        need.unit,
      bestProduct: options[0] ?? null,
      options,
    });
  }

  // 4. Podsumowanie per sklep
  const storeSummaries = buildStoreSummaries(lines);

  // 5. Najtańszy sklep (tylko te ze 100% pokryciem)
  const fullCoverage = storeSummaries.filter(s => s.coveragePercent === 100);
  fullCoverage.sort((a, b) => a.totalCostPln - b.totalCostPln);

  const cheapest = fullCoverage[0] ?? storeSummaries.sort((a, b) => b.coveragePercent - a.coveragePercent)[0] ?? null;

  return {
    lines,
    storeSummaries,
    cheapestStoreId:   cheapest?.storeId ?? null,
    cheapestStoreName: cheapest?.storeName ?? null,
    totalCostPln:      cheapest ? Math.round(cheapest.totalCostPln * 100) / 100 : null,
    missingPrices,
  };
}

// ---------------------------------------------------------------------------
// Podsumowanie per sklep
// ---------------------------------------------------------------------------

function buildStoreSummaries(lines: CartIngredientLine[]): StoreCartSummary[] {
  const storeMap = new Map<string, {
    storeName: string;
    totalCost: number;
    covered:   number;
    missing:   string[];
  }>();

  for (const line of lines) {
    // Zbierz opcje per sklep dla tego składnika
    const byStore = new Map<string, CartProductOption>();
    for (const opt of line.options) {
      const existing = byStore.get(opt.storeId);
      if (!existing || opt.pricePerGram < existing.pricePerGram) {
        byStore.set(opt.storeId, opt);
      }
    }

    // Zaktualizuj sumy per sklep
    for (const [storeId, opt] of byStore) {
      if (!storeMap.has(storeId)) {
        storeMap.set(storeId, {
          storeName: opt.storeName,
          totalCost: 0,
          covered:   0,
          missing:   [],
        });
      }
      const entry = storeMap.get(storeId)!;
      entry.totalCost += opt.totalCostPln;
      entry.covered++;
    }

    // Jeśli żaden sklep nie ma tego składnika — dodaj do missing wszystkim
    if (byStore.size === 0) {
      for (const entry of storeMap.values()) {
        entry.missing.push(line.ingredientName);
      }
    }
  }

  return Array.from(storeMap.entries()).map(([storeId, data]) => ({
    storeId,
    storeName:          data.storeName,
    totalCostPln:       Math.round(data.totalCost * 100) / 100,
    coveragePercent:    lines.length > 0
      ? Math.round((data.covered / lines.length) * 100)
      : 0,
    missingIngredients: data.missing,
  }));
}

// ---------------------------------------------------------------------------
// Optymalizacja koszyka — zamień na 1 sklep
// ---------------------------------------------------------------------------

/**
 * Zwraca koszyk zoptymalizowany pod jeden konkretny sklep.
 * Dla składników niedostępnych w tym sklepie zostaje `bestProduct: null`.
 */
export function optimizeCartForStore(
  cart: CartResult,
  storeId: string
): CartResult {
  const optimizedLines = cart.lines.map(line => {
    const storeOption = line.options.find(o => o.storeId === storeId);
    return {
      ...line,
      bestProduct: storeOption ?? null,
    };
  });

  const missing = optimizedLines
    .filter(l => l.bestProduct === null)
    .map(l => l.ingredientName);

  const total = optimizedLines
    .filter(l => l.bestProduct !== null)
    .reduce((sum, l) => sum + (l.bestProduct!.totalCostPln), 0);

  const store = cart.storeSummaries.find(s => s.storeId === storeId);

  return {
    ...cart,
    lines:             optimizedLines,
    cheapestStoreId:   storeId,
    cheapestStoreName: store?.storeName ?? null,
    totalCostPln:      Math.round(total * 100) / 100,
    missingPrices:     missing,
  };
}

// ---------------------------------------------------------------------------
// Porównanie sklepów (do UI: ekran "Gdzie najtaniej?")
// ---------------------------------------------------------------------------

/**
 * Porównuje sklepy dla podanych przepisów.
 * Zwraca posortowane podsumowania: najtańsze z pełnym pokryciem pierwsze,
 * potem sortowane malejąco po pokryciu.
 */
export async function compareStoresForRecipes(
  recipePortions: Array<{ recipeId: string; portions: number }>
): Promise<StoreCartSummary[]> {
  const cart = await buildCartForRecipes(recipePortions);

  return cart.storeSummaries.sort((a, b) => {
    if (a.coveragePercent !== b.coveragePercent) {
      return b.coveragePercent - a.coveragePercent;
    }
    return a.totalCostPln - b.totalCostPln;
  });
}
