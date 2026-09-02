import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import { Price } from '../model/Price';

/**
 * Returns the current best price for a given store_product_id.
 * Priority:
 * 1. Active flyer price (source = 'flyer', valid_to >= today)
 * 2. Any latest price (fallback)
 * 3. null if no price found
 */
export async function getCurrentPrice(
  storeProductId: string
): Promise<number | null> {
  const pricesCollection = database.get<Price>('prices');
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

  // 1. Active flyer price
  const flyerPrices = await pricesCollection
    .query(
      Q.where('store_product_id', storeProductId),
      Q.where('source', 'flyer'),
      Q.where('valid_to', Q.gte(today))
    )
    .fetch();

  if (flyerPrices.length > 0) {
    const latest = flyerPrices.sort((a, b) => b.updatedAt - a.updatedAt)[0];
    return latest.grossPrice ?? null;
  }

  // 2. Fallback - any latest price
  const allPrices = await pricesCollection
    .query(Q.where('store_product_id', storeProductId))
    .fetch();

  if (allPrices.length > 0) {
    const latest = allPrices.sort((a, b) => b.updatedAt - a.updatedAt)[0];
    return latest.grossPrice ?? null;
  }

  return null;
}

export default getCurrentPrice;
