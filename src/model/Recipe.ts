import { Model, Query } from '@nozbe/watermelondb';
import { text, field, children } from '@nozbe/watermelondb/decorators';

export class Recipe extends Model {
  static table = 'recipes';

  static associations = {
    recipe_ingredients:    { type: 'has_many', foreignKey: 'recipe_id' },
    user_favorite_recipes: { type: 'has_many', foreignKey: 'recipe_id' },
  } as const;

  @text('remote_id')             remoteId?: string;
  @text('title')                 title!: string;
  @text('source_url')            sourceUrl?: string;
  @field('prep_minutes')         prepMinutes?: number;
  @field('portions')             portions!: number;
  @field('protein_per_portion')  proteinPerPortion?: number;
  @field('kcal_per_portion')     kcalPerPortion?: number;
  @field('is_public')            isPublic!: boolean;
  @text('created_by')            createdBy?: string;
  @field('updated_at')           updatedAt!: number;
}
