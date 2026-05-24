import { Database } from '@nozbe/watermelondb';
import SQLiteAdapter from '@nozbe/watermelondb/adapters/sqlite';

import { schema } from '../db/schema';
import {
  Store,
  Ingredient,
  StoreProduct,
  Price,
  IngredientMapping,
  RecipeTag,
  Flyer,
  FlyerItem,
  Receipt,
  ReceiptItem,
  Recipe,
  RecipeIngredient,
  UserIngredientPreference,
  UserFavoriteRecipe,
} from './index';

const adapter = new SQLiteAdapter({
  schema,
  dbName: 'CheapEat',
  jsi: false,
  onSetUpError: error => {
    console.error('Database setup error:', error);
  },
});

export const database = new Database({
  adapter,
  modelClasses: [
    Store,
    Ingredient,
    StoreProduct,
    Price,
    IngredientMapping,
    RecipeTag,
    Flyer,
    FlyerItem,
    Receipt,
    ReceiptItem,
    Recipe,
    RecipeIngredient,
    UserIngredientPreference,
    UserFavoriteRecipe,
  ],
});
