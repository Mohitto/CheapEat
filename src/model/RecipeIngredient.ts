import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Recipe } from './Recipe';
import { Ingredient } from './Ingredient';

export class RecipeIngredient extends Model {
  static table = 'recipe_ingredients';

  static associations = {
    recipes:     { type: 'belongs_to', key: 'recipe_id' },
    ingredients: { type: 'belongs_to', key: 'ingredient_id' },
  } as const;

  @text('remote_id')     remoteId?: string;
  @text('recipe_id')     recipeId!: string;
  @text('ingredient_id') ingredientId!: string;
  @field('amount')       amount!: number;
  @text('unit')          unit!: string;
  @field('updated_at')   updatedAt!: number;

  @relation('recipes',     'recipe_id')     recipe!: Relation<Recipe>;
  @relation('ingredients', 'ingredient_id') ingredient!: Relation<Ingredient>;
}
