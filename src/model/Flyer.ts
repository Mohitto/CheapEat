import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Store } from './Store';

export class Flyer extends Model {
  static table = 'flyers';

  static associations = {
    stores:      { type: 'belongs_to', key: 'store_id' },
    flyer_items: { type: 'has_many', foreignKey: 'flyer_id' },
  } as const;

  @text('remote_id')   remoteId!: string;
  @text('store_id')    storeId!: string;
  @text('valid_from')  validFrom!: string;
  @text('valid_to')    validTo!: string;
  @text('file_url')    fileUrl?: string;
  @field('updated_at') updatedAt!: number;

  @relation('stores', 'store_id') store!: Relation<Store>;
}
