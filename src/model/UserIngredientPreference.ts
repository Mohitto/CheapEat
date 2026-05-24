import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Ingredient } from './Ingredient';

export class UserIngredientPreference extends Model {
  static table = 'user_ingredient_preferences';

  static associations = {
    ingredients: { type: 'belongs_to', key: 'ingredient_id' },
  } as const;

  @text('remote_id')     remoteId?: string;
  @text('user_id')       userId!: string;
  @text('ingredient_id') ingredientId!: string;
  @text('preference')    preference!: string; // 'like' | 'medium' | 'additive' | 'forbidden'
  @field('updated_at')   updatedAt!: number;

  @relation('ingredients', 'ingredient_id') ingredient!: Relation<Ingredient>;
}
