import { Database } from '@nozbe/watermelondb';
import SQLiteAdapter from '@nozbe/watermelondb/adapters/sqlite';

import schema from './schema';
import { Sklep } from './Sklep';
import { ProduktSklepu } from './ProduktSklepu';

const adapter = new SQLiteAdapter({
  schema,
  // (Optional) Database name. Default is 'watermelon'
  dbName: 'CheapEat',
  // (Optional) Syntax highlighter support
  jsi: false,
  onSetUpError: error => {
    // Database failed to load -- i.e. low disk space.
    console.error('Database setup error:', error);
  },
});

export const database = new Database({
  adapter,
  modelClasses: [Sklep, ProduktSklepu],
});
