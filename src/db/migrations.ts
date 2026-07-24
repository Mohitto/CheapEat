import { schemaMigrations, addColumns } from '@nozbe/watermelondb/Schema/migrations';

/**
 * WatermelonDB migrations.
 * ZASADA: nigdy nie modyfikuj istniejących kroków — tylko dodawaj nowe.
 */
export const migrations = schemaMigrations({
  migrations: [
    {
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
  ],
});
