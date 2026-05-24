import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Recipe } from './Recipe';

export class UserFavoriteRecipe extends Model {
  static table = 'user_favorite_recipes';

  static associations = {
    recipes: { type: 'belongs_to', key: 'recipe_id' },
  } as const;

  @text('remote_id')   remoteId?: string;
  @text('user_id')     userId!: string;
  @text('recipe_id')   recipeId!: string;
  @field('updated_at') updatedAt!: number;

  @relation('recipes', 'recipe_id') recipe!: Relation<Recipe>;
}
