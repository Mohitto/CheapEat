import { appSchema, tableSchema } from '@nozbe/watermelondb';

export default appSchema({
  version: 1,
  tables: [
    tableSchema({
      name: 'sklepy',
      columns: [
        { name: 'nazwa', type: 'string' },
        { name: 'logo_url', type: 'string' },
        { name: 'status_aktywny', type: 'boolean' },
      ],
    }),
    tableSchema({
      name: 'produkty_sklepu',
      columns: [
        { name: 'sklep_id', type: 'string', isIndexed: true },
        { name: 'nazwa_sklepowa', type: 'string' },
        { name: 'kod_kreskowy', type: 'string' },
        { name: 'jednostka', type: 'string' },
        { name: 'ilosc_na_jednostke', type: 'number' },
      ],
    }),
  ],
});
