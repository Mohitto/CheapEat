import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Ingredient } from './Ingredient';
import { StoreProduct } from './StoreProduct';

export class IngredientMapping extends Model {
  static table = 'ingredient_mappings';

  static associations = {
    ingredients:    { type: 'belongs_to', key: 'ingredient_id' },
    store_products: { type: 'belongs_to', key: 'store_product_id' },
  } as const;

  @text('remote_id')         remoteId!: string;
  @text('ingredient_id')     ingredientId!: string;
  @text('store_product_id')  storeProductId!: string;
  @field('conversion_factor') conversionFactor!: number;
  @field('priority')         priority!: number;
  @field('updated_at')       updatedAt!: number;

  @relation('ingredients',    'ingredient_id')    ingredient!: Relation<Ingredient>;
  @relation('store_products', 'store_product_id') storeProduct!: Relation<StoreProduct>;
}
