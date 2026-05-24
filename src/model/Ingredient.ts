import { Model, Query } from '@nozbe/watermelondb';
import { text, field, children } from '@nozbe/watermelondb/decorators';

export class Ingredient extends Model {
  static table = 'ingredients';

  static associations = {
    ingredient_mappings:         { type: 'has_many', foreignKey: 'ingredient_id' },
    recipe_ingredients:          { type: 'has_many', foreignKey: 'ingredient_id' },
    user_ingredient_preferences: { type: 'has_many', foreignKey: 'ingredient_id' },
  } as const;

  @text('remote_id')        remoteId!: string;
  @text('name')             name!: string;
  @field('protein_per_100g') proteinPer100g?: number;
  @field('kcal_per_100g')   kcalPer100g?: number;
  @field('updated_at')      updatedAt!: number;
}
