import { appSchema, tableSchema } from '@nozbe/watermelondb';

export const schema = appSchema({
  version: 1,
  tables: [

    // ── READ-ONLY ────────────────────────────────────────────
    tableSchema({
      name: 'stores',
      columns: [
        { name: 'remote_id',   type: 'string' },
        { name: 'name',        type: 'string' },
        { name: 'logo_url',    type: 'string', isOptional: true },
        { name: 'website_url', type: 'string', isOptional: true },
        { name: 'is_active',   type: 'boolean' },
        { name: 'updated_at',  type: 'number' },
      ],
    }),
    tableSchema({
      name: 'ingredients',
      columns: [
        { name: 'remote_id',        type: 'string' },
        { name: 'name',             type: 'string' },
        { name: 'protein_per_100g', type: 'number', isOptional: true },
        { name: 'kcal_per_100g',    type: 'number', isOptional: true },
        { name: 'updated_at',       type: 'number' },
      ],
    }),
    tableSchema({
      name: 'store_products',
      columns: [
        { name: 'remote_id',   type: 'string' },
        { name: 'store_id',    type: 'string', isIndexed: true },
        { name: 'name',        type: 'string' },
        { name: 'unit',        type: 'string', isOptional: true },
        { name: 'unit_amount', type: 'number', isOptional: true },
        { name: 'updated_at',  type: 'number' },
      ],
    }),
    tableSchema({
      name: 'prices',
      columns: [
        { name: 'remote_id',        type: 'string' },
        { name: 'store_product_id', type: 'string', isIndexed: true },
        { name: 'gross_price',      type: 'number' },
        { name: 'source',           type: 'string' },
        { name: 'valid_from',       type: 'string', isOptional: true },
        { name: 'valid_to',         type: 'string', isOptional: true },
        { name: 'updated_at',       type: 'number' },
      ],
    }),
    tableSchema({
      name: 'ingredient_mappings',
      columns: [
        { name: 'remote_id',         type: 'string' },
        { name: 'ingredient_id',     type: 'string', isIndexed: true },
        { name: 'store_product_id',  type: 'string', isIndexed: true },
        { name: 'conversion_factor', type: 'number' },
        { name: 'priority',          type: 'number' },
        { name: 'updated_at',        type: 'number' },
      ],
    }),
    tableSchema({
      name: 'recipe_tags',
      columns: [
        { name: 'remote_id',  type: 'string' },
        { name: 'name',       type: 'string' },
        { name: 'updated_at', type: 'number' },
      ],
    }),
    tableSchema({
      name: 'flyers',
      columns: [
        { name: 'remote_id',  type: 'string' },
        { name: 'store_id',   type: 'string', isIndexed: true },
        { name: 'valid_from', type: 'string' },
        { name: 'valid_to',   type: 'string' },
        { name: 'file_url',   type: 'string', isOptional: true },
        { name: 'updated_at', type: 'number' },
      ],
    }),
    tableSchema({
      name: 'flyer_items',
      columns: [
        { name: 'remote_id',   type: 'string' },
        { name: 'flyer_id',    type: 'string', isIndexed: true },
        { name: 'store_name',  type: 'string' },
        { name: 'price',       type: 'number' },
        { name: 'unit',        type: 'string', isOptional: true },
        { name: 'unit_amount', type: 'number', isOptional: true },
        { name: 'notes',       type: 'string', isOptional: true },
        { name: 'updated_at',  type: 'number' },
      ],
    }),

    // ── USER DATA ─────────────────────────────────────────────
    tableSchema({
      name: 'receipts',
      columns: [
        { name: 'remote_id',    type: 'string', isOptional: true },
        { name: 'user_id',      type: 'string', isIndexed: true },
        { name: 'store_id',     type: 'string', isOptional: true },
        { name: 'receipt_date', type: 'string' },
        { name: 'image_url',    type: 'string', isOptional: true },
        { name: 'ocr_status',   type: 'string' },
        { name: 'total_amount', type: 'number', isOptional: true },
        { name: 'updated_at',   type: 'number' },
      ],
    }),
    tableSchema({
      name: 'receipt_items',
      columns: [
        { name: 'remote_id',   type: 'string', isOptional: true },
        { name: 'receipt_id',  type: 'string', isIndexed: true },
        { name: 'store_name',  type: 'string' },
        { name: 'quantity',    type: 'number' },
        { name: 'unit_price',  type: 'number', isOptional: true },
        { name: 'total_price', type: 'number' },
        { name: 'unit',        type: 'string', isOptional: true },
        { name: 'updated_at',  type: 'number' },
      ],
    }),
    tableSchema({
      name: 'recipes',
      columns: [
        { name: 'remote_id',           type: 'string', isOptional: true },
        { name: 'title',               type: 'string' },
        { name: 'source_url',          type: 'string', isOptional: true },
        { name: 'prep_minutes',        type: 'number', isOptional: true },
        { name: 'portions',            type: 'number' },
        { name: 'protein_per_portion', type: 'number', isOptional: true },
        { name: 'kcal_per_portion',    type: 'number', isOptional: true },
        { name: 'is_public',           type: 'boolean' },
        { name: 'created_by',          type: 'string', isOptional: true },
        { name: 'updated_at',          type: 'number' },
      ],
    }),
    tableSchema({
      name: 'recipe_ingredients',
      columns: [
        { name: 'remote_id',     type: 'string', isOptional: true },
        { name: 'recipe_id',     type: 'string', isIndexed: true },
        { name: 'ingredient_id', type: 'string', isIndexed: true },
        { name: 'amount',        type: 'number' },
        { name: 'unit',          type: 'string' },
        { name: 'updated_at',    type: 'number' },
      ],
    }),
    tableSchema({
      name: 'user_ingredient_preferences',
      columns: [
        { name: 'remote_id',     type: 'string', isOptional: true },
        { name: 'user_id',       type: 'string', isIndexed: true },
        { name: 'ingredient_id', type: 'string', isIndexed: true },
        { name: 'preference',    type: 'string' },
        { name: 'updated_at',    type: 'number' },
      ],
    }),
    tableSchema({
      name: 'user_favorite_recipes',
      columns: [
        { name: 'remote_id',  type: 'string', isOptional: true },
        { name: 'user_id',    type: 'string', isIndexed: true },
        { name: 'recipe_id',  type: 'string', isIndexed: true },
        { name: 'updated_at', type: 'number' },
      ],
    }),

  ],
});
