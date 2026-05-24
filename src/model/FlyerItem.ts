import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Flyer } from './Flyer';

export class FlyerItem extends Model {
  static table = 'flyer_items';

  static associations = {
    flyers: { type: 'belongs_to', key: 'flyer_id' },
  } as const;

  @text('remote_id')   remoteId!: string;
  @text('flyer_id')    flyerId!: string;
  @text('store_name')  storeName!: string;
  @field('price')      price!: number;
  @text('unit')        unit?: string;
  @field('unit_amount') unitAmount?: number;
  @text('notes')       notes?: string;
  @field('updated_at') updatedAt!: number;

  @relation('flyers', 'flyer_id') flyer!: Relation<Flyer>;
}
