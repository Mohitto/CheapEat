import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { Price } from '../model/Price';

/** Źródła cen promocyjnych — obowiązują tylko w oknie ważności gazetki. */
const PROMO_SOURCES = ['flyer-ocr', 'flyer-ssr', 'flyer'];

export type PriceInfo = {
  grossPricePln: number;
  source: string;
  /** true, gdy to cena z gazetki obowiązująca dzisiaj. */
  isPromo: boolean;
  /** Cena regularna, gdy promocja jest tańsza — do pokazania "było / jest". */
  regularPricePln: number | null;
};

/**
 * Zwraca cenę, którą realnie zapłacisz dzisiaj za dany produkt sklepowy.
 *
 * 1. Cena promocyjna z gazetki, ale WYŁĄCZNIE gdy dzisiejsza data mieści
 *    się w okresie jej obowiązywania.
 * 2. Gdy promocja wygasła (albo jej nie ma) — cena regularna ze sklepu.
 *
 * Wcześniej krok 2 brał po prostu "najnowszą cenę wg updated_at", bez
 * patrzenia na daty ważności, więc wygasła promocja z gazetki nadal
 * wyświetlała się jako aktualna. Promocja ma wygasać sama, a apka ma
 * wtedy wracać do ceny sprzed promocji.
 */
export async function getCurrentPriceInfo(
  storeProductId: string
): Promise<PriceInfo | null> {
  const prices = await database
    .get<Price>('prices')
    .query(Q.where('store_product_id', storeProductId))
    .fetch();

  if (prices.length === 0) return null;

  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  const isCurrentlyValid = (p: Price) => {
    if (p.validFrom && p.validFrom > today) return false; // gazetka zaczyna się dopiero za jakiś czas
    if (p.validTo && p.validTo < today) return false;     // promocja już wygasła
    return true;
  };

  const newestFirst = (a: Price, b: Price) => b.updatedAt - a.updatedAt;

  const regular = prices
    .filter(p => !PROMO_SOURCES.includes(p.source) && isCurrentlyValid(p))
    .sort(newestFirst)[0];
  const regularPricePln = regular?.grossPrice ?? null;

  const promo = prices
    .filter(p => PROMO_SOURCES.includes(p.source) && isCurrentlyValid(p))
    .sort(newestFirst)[0];

  if (promo?.grossPrice != null) {
    return {
      grossPricePln: promo.grossPrice,
      source: promo.source,
      isPromo: true,
      // Cena regularna ma sens jako odniesienie tylko wtedy, gdy promocja
      // jest od niej tańsza — inaczej pokazywalibyśmy mylące "było taniej".
      regularPricePln:
        regularPricePln != null && regularPricePln > promo.grossPrice ? regularPricePln : null,
    };
  }

  if (regular?.grossPrice != null) {
    return {
      grossPricePln: regular.grossPrice,
      source: regular.source,
      isPromo: false,
      regularPricePln: null,
    };
  }

  return null;
}

/** Sama kwota — wygodne tam, gdzie szczegóły promocji nie są potrzebne. */
export async function getCurrentPrice(
  storeProductId: string
): Promise<number | null> {
  const info = await getCurrentPriceInfo(storeProductId);
  return info?.grossPricePln ?? null;
}

export default getCurrentPrice;
