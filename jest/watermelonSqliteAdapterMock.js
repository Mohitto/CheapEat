// Jest nie ma dostępu do natywnego mostka SQLite (WMDatabaseBridge) — działa
// w Node, nie na urządzeniu/symulatorze. Podmieniamy SQLiteAdapter na
// LokiJSAdapter w trybie czysto pamięciowym, żeby testy mogły skonstruować
// WatermelonDB Database bez natywnego modułu.
const LokiJSAdapter = require('@nozbe/watermelondb/adapters/lokijs').default;

module.exports = class SQLiteAdapterMock extends LokiJSAdapter {
  constructor({ schema, migrations }) {
    super({
      schema,
      migrations,
      useWebWorker: false,
      useIncrementalIndexedDB: false,
    });
  }
};
module.exports.default = module.exports;
