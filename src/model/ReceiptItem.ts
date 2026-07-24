import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Receipt } from './Receipt';

export class ReceiptItem extends Model {
  static table = 'receipt_items';

  static associations = {
    receipts: { type: 'belongs_to', key: 'receipt_id' },
  } as const;

  @text('remote_id')        remoteId?: string;
  @text('receipt_id')       receiptId!: string;
  @text('store_product_id') storeProductId?: string;
  @text('raw_name')         rawName!: string;
  @text('matched_name')     matchedName?: string;
  @field('gross_price')     grossPrice?: number;
  @field('quantity')        quantity!: number;
  @text('unit')             unit?: string;
  @field('confidence')      confidence?: number;
  @field('updated_at')      updatedAt!: number;

  @relation('receipts', 'receipt_id') receipt!: Relation<Receipt>;
}
