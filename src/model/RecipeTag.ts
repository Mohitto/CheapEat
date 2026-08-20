import { Model } from '@nozbe/watermelondb';
import { text, field } from '@nozbe/watermelondb/decorators';

export class RecipeTag extends Model {
  static table = 'recipe_tags';

  @text('remote_id')   remoteId!: string;
  @text('name')        name!: string;
  @field('updated_at') updatedAt!: number;
}
