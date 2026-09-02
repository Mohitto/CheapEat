/**
 * mappingService.ts
 * 
 * Logika łączenia produktów sklepowych ze składnikami bazowymi.
 * 
 * Przepływ:
 * 1. Scraper pobiera produkt ze sklepu (np. "Kurczak Filet Biedronka 500g")
 * 2. normalizeProductName() czyci nazwę -> "kurczak pierś"
 * 3. matchProductToIngredient() szuka w tabeli ingredients
 * 4. Jeśli znaleziony -> createMapping() tworzy wiązanie w ingredient_mappings
 * 5. calculateConversionFactor() oblicza współczynnik (np. 500g -> factor=5 dla 100g)
 */
import { supabase } from '../lib/supabase';
import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { IngredientMapping } from '../model/IngredientMapping';
import { matchProductToIngredient } from './ingredientService';

// ---------------------------------------------------------------------------
// Typy
// ---------------------------------------------------------------------------

export type MappingInput = {
  ingredientId: string;
  storeProductId: string;
  conversionFactor?: number;  // domyślnie 1.0
  priority?: number;          // niższy = wyższy priorytet, domyślnie 10
};

export type MappingResult = {
  id: string;
  ingredientName: string;
  productName: string;
  storeName: string;
  conversionFactor: number;
  priority: number;
};

// ---------------------------------------------------------------------------
// Obliczanie współczynnika przeliczenia
// ---------------------------------------------------------------------------

/**
 * Oblicza conversion_factor na podstawie gramatury opakowania.
 * 
 * Factor = unitAmount / 100
 * Przykład: opakowanie 500g kurczaka -> factor = 5.0
 * Dzięki temu: cena_opakowania / unitAmount * 100 * factor = cena_za_100g
 * 
 * Jeśli unitAmount nieznany -> factor = 1.0 (cena traktowana jako za 100g)
 */
export function calculateConversionFactor(unitAmount: number | null): number {
  if (!unitAmount || unitAmount <= 0) return 1.0;
  return Math.round((unitAmount / 100) * 1000) / 1000; // precyzja do 3 miejsc
}

// ---------------------------------------------------------------------------
// Tworzenie mapowania (przez Supabase RPC — wymaga service role)
// ---------------------------------------------------------------------------

/**
 * Tworzy lub aktualizuje mapowanie produkt -> składnik w Supabase.
 * Używa RPC admin_upsert_mapping (SECURITY DEFINER).
 */
export async function createMapping(input: MappingInput): Promise<string | null> {
  const { data, error } = await supabase.rpc('admin_upsert_mapping', {
    p_ingredient_id:     input.ingredientId,
    p_store_product_id:  input.storeProductId,
    p_conversion_factor: input.conversionFactor ?? 1.0,
    p_priority:          input.priority ?? 10,
  });

  if (error) {
    console.error('[mappingService] createMapping error:', error.message);
    return null;
  }

  return data as string;
}

// ---------------------------------------------------------------------------
// Auto-mapowanie: produkt -> składnik przez normalizację nazwy
// ---------------------------------------------------------------------------

/**
 * Próbuje automatycznie zmapować produkt sklepowy do składnika bazowego.
 * 
 * 1. Pobiera nazwę produktu z lokalnej bazy
 * 2. Normalizuje i szuka dopasowania w ingredients
 * 3. Jeśli znalaziony -> tworzy mapowanie z wyliczonym conversion_factor
 * 
 * Zwraca ID mapowania lub null jeśli nie udało się dopasować.
 */
export async function autoMapProduct(
  storeProductId: string,
  unitAmount?: number
): Promise<string | null> {
  // Pobierz produkt z lokalnej bazy
  let productName: string;
  try {
    const product = await database.get('store_products').find(storeProductId);
    productName = (product as any).name as string;
  } catch {
    console.warn('[mappingService] autoMapProduct: produkt nie znaleziony lokalnie', storeProductId);
    return null;
  }

  // Dopasuj do składnika
  const ingredient = await matchProductToIngredient(productName);
  if (!ingredient) {
    console.log(`[mappingService] Brak dopasowania dla: "${productName}"`);
    return null;
  }

  const conversionFactor = calculateConversionFactor(unitAmount ?? null);

  console.log(`[mappingService] Auto-map: "${productName}" -> "${ingredient.name}" (factor: ${conversionFactor})`);

  return createMapping({
    ingredientId:    ingredient.id,
    storeProductId,
    conversionFactor,
    priority:        10,
  });
}

// ---------------------------------------------------------------------------
// Odczyt mapowań (lokalny — WatermelonDB)
// ---------------------------------------------------------------------------

/**
 * Zwraca wszystkie mapowania dla danego składnika, posortowane priorytetem.
 */
export async function getMappingsByIngredient(
  ingredientId: string
): Promise<IngredientMapping[]> {
  return database
    .get<IngredientMapping>('ingredient_mappings')
    .query(
      Q.where('ingredient_id', ingredientId),
      Q.sortBy('priority', Q.asc)
    )
    .fetch();
}

/**
 * Zwraca mapowanie dla konkretnego produktu sklepowego.
 */
export async function getMappingByProduct(
  storeProductId: string
): Promise<IngredientMapping | null> {
  const results = await database
    .get<IngredientMapping>('ingredient_mappings')
    .query(Q.where('store_product_id', storeProductId))
    .fetch();
  return results.length > 0 ? results[0] : null;
}

/**
 * Sprawdza czy produkt jest już zmapowany do jakiegokolwiek składnika.
 */
export async function isProductMapped(storeProductId: string): Promise<boolean> {
  const result = await getMappingByProduct(storeProductId);
  return result !== null;
}

// ---------------------------------------------------------------------------
// Bulk auto-mapowanie (używane przez scraper po wstawieniu nowych produktów)
// ---------------------------------------------------------------------------

/**
 * Próbuje auto-mapować wszystkie niezamapowane produkty danego sklepu.
 * Zwraca statystyki: ile zmapowano, ile pominęto.
 */
export async function autoMapUnmappedProducts(storeId: string): Promise<{
  mapped: number;
  skipped: number;
  failed: number;
}> {
  const products = await database
    .get('store_products')
    .query(Q.where('store_id', storeId))
    .fetch();

  let mapped = 0, skipped = 0, failed = 0;

  for (const product of products) {
    const alreadyMapped = await isProductMapped(product.id);
    if (alreadyMapped) { skipped++; continue; }

    const unitAmount = (product as any).unitAmount as number | undefined;
    const result = await autoMapProduct(product.id, unitAmount);

    if (result) mapped++;
    else failed++;
  }

  console.log(`[mappingService] autoMapUnmappedProducts: mapped=${mapped}, skipped=${skipped}, failed=${failed}`);
  return { mapped, skipped, failed };
}
