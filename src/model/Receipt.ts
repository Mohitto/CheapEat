import { Model, Query, Relation } from '@nozbe/watermelondb';
import { text, field, relation, children } from '@nozbe/watermelondb/decorators';
import { Store } from './Store';

export class Receipt extends Model {
  static table = 'receipts';

  static associations = {
    stores:        { type: 'belongs_to', key: 'store_id' },
    receipt_items: { type: 'has_many', foreignKey: 'receipt_id' },
  } as const;

  @text('remote_id')    remoteId?: string;
  @text('user_id')      userId!: string;
  @text('store_id')     storeId?: string;
  @text('receipt_date') receiptDate!: string;
  @text('image_url')    imageUrl?: string;
  @text('ocr_status')   ocrStatus!: string;
  @field('total_amount') totalAmount?: number;
  @field('updated_at')  updatedAt!: number;

  @relation('stores', 'store_id') store!: Relation<Store>;
}
