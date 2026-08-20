import { schemaMigrations, addColumns, unsafeExecuteSql } from '@nozbe/watermelondb/Schema/migrations';

/**
 * WatermelonDB migrations.
 * ZASADA: nigdy nie modyfikuj istniejących kroków — tylko dodawaj nowe.
 */
export const migrations = schemaMigrations({
  migrations: [
    {
      // v1 -> v2: dodano index na ingredient_mappings.priority i ingredients.name
      toVersion: 2,
      steps: [
        addColumns({
          table: 'ingredient_mappings',
          columns: [
            { name: 'priority', type: 'number', isIndexed: true },
          ],
        }),
        addColumns({
          table: 'ingredients',
          columns: [
            { name: 'name', type: 'string', isIndexed: true },
          ],
        }),
      ],
    },
    {
      // v2 -> v3: receipt_items przepisane pod OCR
      // Stare kolumny (store_name, unit_price, total_price) zastąpione przez
      // (store_product_id, raw_name, matched_name, gross_price, confidence)
      toVersion: 3,
      steps: [
        addColumns({
          table: 'receipt_items',
          columns: [
            { name: 'store_product_id', type: 'string', isOptional: true },
            { name: 'raw_name',         type: 'string' },
            { name: 'matched_name',     type: 'string', isOptional: true },
            { name: 'gross_price',      type: 'number', isOptional: true },
            { name: 'confidence',       type: 'number', isOptional: true },
          ],
        }),
      ],
    },
    {
      // v3 -> v4: funkcja paragonów (OCR) porzucona — usuwamy receipts/receipt_items
      toVersion: 4,
      steps: [
        unsafeExecuteSql('DROP TABLE IF EXISTS receipts;'),
        unsafeExecuteSql('DROP TABLE IF EXISTS receipt_items;'),
      ],
    },
  ],
});
