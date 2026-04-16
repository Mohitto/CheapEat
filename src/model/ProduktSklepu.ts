import { Model, Relation } from '@nozbe/watermelondb';
import { text, field, relation } from '@nozbe/watermelondb/decorators';
import { Sklep } from './Sklep';

export class ProduktSklepu extends Model {
  static table = 'produkty_sklepu';

  static associations = {
    sklepy: { type: 'belongs_to', key: 'sklep_id' },
  } as const;

  @text('nazwa_sklepowa') nazwaSklepowa!: string;
  @text('kod_kreskowy') kodKreskowy!: string;
  @text('jednostka') jednostka!: string;
  @field('ilosc_na_jednostke') iloscNaJednostke!: number;

  @relation('sklepy', 'sklep_id') sklep!: Relation<Sklep>;
}
