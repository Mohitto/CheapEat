import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { StoreProduct } from './StoreProduct';

export class Price extends Model {
  static table = 'prices';

  static associations = {
    store_products: { type: 'belongs_to', key: 'store_product_id' },
  } as const;

  @text('remote_id')        remoteId!: string;
  @text('store_product_id') storeProductId!: string;
  @field('gross_price')     grossPrice!: number;
  @text('source')           source!: string;
  @text('valid_from')       validFrom?: string;
  @text('valid_to')         validTo?: string;
  @field('updated_at')      updatedAt!: number;

  @relation('store_products', 'store_product_id') storeProduct!: Relation<StoreProduct>;
}
