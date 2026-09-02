import { Model } from '@nozbe/watermelondb';
import { text, field } from '@nozbe/watermelondb/decorators';

export class Store extends Model {
  static table = 'stores';

  static associations = {
    store_products: { type: 'has_many', foreignKey: 'store_id' },
    flyers:         { type: 'has_many', foreignKey: 'store_id' },
  } as const;

  @text('remote_id')   remoteId!: string;
  @text('name')        name!: string;
  @text('logo_url')    logoUrl?: string;
  @text('website_url') websiteUrl?: string;
  @field('is_active')  isActive!: boolean;
  @field('updated_at') updatedAt!: number;
}
