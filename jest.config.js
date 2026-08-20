module.exports = {
  preset: '@react-native/jest-preset',
  moduleNameMapper: {
    '^@react-native-async-storage/async-storage$':
      '@react-native-async-storage/async-storage/jest/async-storage-mock',
    '^@nozbe/watermelondb/adapters/sqlite$': '<rootDir>/jest/watermelonSqliteAdapterMock.js',
    '^@supabase/supabase-js$': '<rootDir>/jest/supabaseJsMock.js',
  },
  transformIgnorePatterns: [
    'node_modules/(?!(@react-native|react-native|@react-navigation|@nozbe|react-native-.*)/)',
  ],
};
