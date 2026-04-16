import { Model, Query, Relation } from '@nozbe/watermelondb';
import { text, field, children } from '@nozbe/watermelondb/decorators';
import { ProduktSklepu } from './ProduktSklepu';

export class Sklep extends Model {
  static table = 'sklepy';

  static associations = {
    produkty_sklepu: { type: 'has_many', foreignKey: 'sklep_id' },
  } as const;

  @text('nazwa') nazwa!: string;
  @text('logo_url') logoUrl!: string;
  @field('status_aktywny') statusAktywny!: boolean;

  @children('produkty_sklepu') produktySklepu!: Query<ProduktSklepu>;
}
