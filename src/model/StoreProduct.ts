import { Model, Query, Relation } from '@nozbe/watermelondb';
import { text, field, relation, children } from '@nozbe/watermelondb/decorators';
import { Store } from './Store';

export class StoreProduct extends Model {
  static table = 'store_products';

  static associations = {
    stores:              { type: 'belongs_to', key: 'store_id' },
    prices:              { type: 'has_many', foreignKey: 'store_product_id' },
    ingredient_mappings: { type: 'has_many', foreignKey: 'store_product_id' },
  } as const;

  @text('remote_id')   remoteId!: string;
  @text('store_id')    storeId!: string;
  @text('name')        name!: string;
  @text('unit')        unit?: string;
  @field('unit_amount') unitAmount?: number;
  @field('updated_at') updatedAt!: number;

  @relation('stores', 'store_id') store!: Relation<Store>;
}
