import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import Ingredient from '../model/Ingredient';
import IngredientMapping from '../model/IngredientMapping';

// ---------------------------------------------------------------------------
// Normalizacja nazwy produktu -> dopasowanie do składnika bazowego
// ---------------------------------------------------------------------------

/**
 * Normalizuje surową nazwę produktu ze sklepu/paragonu do postaci
 * używanej w tabeli ingredients.
 *
 * Przykłady:
 *   "Kurczak Filet z piersi 500g Biedronka" -> "kurczak pierś"
 *   "MLEKO UHT 3,2% 1L" -> "mleko 3.2%"
 *   "Łosoś wędzony plastry" -> "łosoś"
 */
export function normalizeProductName(rawName: string): string {
  return rawName
    .toLowerCase()
    .normalize('NFD') // rozbija znaki diakrytyczne na base + kombinujący
    // Nie strip diakrytyki — zachowaj polskie znaki
    .normalize('NFC')
    // Usuń ilości i jednostki: 500g, 1L, 250ml, 1kg, 2szt
    .replace(/\d+\s*(g|kg|ml|l|szt|op|pcs)\b/gi, '')
    // Usuń procenty stojące samotnie (np. "3,2%" -> zostaje jako część nazwy mleka)
    // Normalizuj przecinek na kropkę w procentach
    .replace(/(\d+),(\d+)%/g, '$1.$2%')
    // Usuń nazwy sklepów
    .replace(/\b(biedronka|lidl|aldi|auchan|kaufland|netto|dino)\b/gi, '')
    // Usuń typowe słowa-śmieci
    .replace(/\b(filet|plastry|kawałki|mielony|mielona|świeży|świeża|mrożony|mrożona|wędzony|wędzona|gotowy|gotowa|z kością|bez kości)\b/gi, '')
    // Kolaps whitespace
    .replace(/\s+/g, ' ')
    .trim();
}

// ---------------------------------------------------------------------------
// Wyszukiwanie składnika po nazwie (lokalna baza WatermelonDB)
// ---------------------------------------------------------------------------

/**
 * Szuka składnika w lokalnej bazie po znormalizowanej nazwie.
 * Zwraca pierwszy pasujący lub null.
 */
export async function findIngredientByName(
  normalizedName: string
): Promise<Ingredient | null> {
  const results = await database
    .get<Ingredient>('ingredients')
    .query(Q.where('name', Q.like(`%${Q.sanitizeLikeString(normalizedName)}%`)))
    .fetch();

  return results.length > 0 ? results[0] : null;
}

/**
 * Próbuje dopasować surową nazwę produktu do składnika bazowego.
 * 1. Normalizuje nazwę
 * 2. Szuka exact match
 * 3. Szuka partial match (LIKE)
 * 4. Zwraca null jeśli brak dopasowania
 */
export async function matchProductToIngredient(
  rawProductName: string
): Promise<Ingredient | null> {
  const normalized = normalizeProductName(rawProductName);

  // Exact match najpierw
  const exact = await database
    .get<Ingredient>('ingredients')
    .query(Q.where('name', normalized))
    .fetch();

  if (exact.length > 0) return exact[0];

  // Partial match
  return findIngredientByName(normalized);
}

// ---------------------------------------------------------------------------
// Pobranie aktualnej ceny składnika (przez ingredient_mappings -> prices)
// ---------------------------------------------------------------------------

/**
 * Zwraca wszystkie mapowania produktów dla danego składnika,
 * posortowane wg priorytetu (niższy numer = wyższy priorytet).
 */
export async function getIngredientMappings(
  ingredientId: string
): Promise<IngredientMapping[]> {
  const mappings = await database
    .get<IngredientMapping>('ingredient_mappings')
    .query(
      Q.where('ingredient_id', ingredientId),
      Q.sortBy('priority', Q.asc)
    )
    .fetch();

  return mappings;
}

/**
 * Zwraca współczynnik przeliczenia jednostek między produktem
 * a składnikiem (np. opakowanie 500g kurczaka ma factor = 5
 * żeby przeliczyć cenę na 100g).
 */
export function calculateIngredientCostPer100g(
  grossPrice: number,
  unitAmount: number, // gramów/ml w opakowaniu
  conversionFactor: number // z ingredient_mappings
): number {
  if (unitAmount <= 0 || conversionFactor <= 0) return 0;
  // cena za gram * 100 * współczynnik normalizacji
  return (grossPrice / unitAmount) * 100 * conversionFactor;
}
