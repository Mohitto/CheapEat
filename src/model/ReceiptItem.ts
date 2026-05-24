import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Receipt } from './Receipt';

export class ReceiptItem extends Model {
  static table = 'receipt_items';

  static associations = {
    receipts: { type: 'belongs_to', key: 'receipt_id' },
  } as const;

  @text('remote_id')   remoteId?: string;
  @text('receipt_id')  receiptId!: string;
  @text('store_name')  storeName!: string;
  @field('quantity')   quantity!: number;
  @field('unit_price') unitPrice?: number;
  @field('total_price') totalPrice!: number;
  @text('unit')        unit?: string;
  @field('updated_at') updatedAt!: number;

  @relation('receipts', 'receipt_id') receipt!: Relation<Receipt>;
}
