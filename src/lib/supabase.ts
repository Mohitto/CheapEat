import 'react-native-url-polyfill/auto';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import type { Database } from '../types/database.types';

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const SUPABASE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '';

export const supabase = createClient<Database>(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

// Typy pomocnicze
export type Store                    = Database['public']['Tables']['stores']['Row'];
export type Ingredient               = Database['public']['Tables']['ingredients']['Row'];
export type StoreProduct             = Database['public']['Tables']['store_products']['Row'];
export type Price                    = Database['public']['Tables']['prices']['Row'];
export type IngredientMapping        = Database['public']['Tables']['ingredient_mappings']['Row'];
export type Flyer                    = Database['public']['Tables']['flyers']['Row'];
export type FlyerItem                = Database['public']['Tables']['flyer_items']['Row'];
export type Receipt                  = Database['public']['Tables']['receipts']['Row'];
export type ReceiptItem              = Database['public']['Tables']['receipt_items']['Row'];
export type Recipe                   = Database['public']['Tables']['recipes']['Row'];
export type RecipeIngredient         = Database['public']['Tables']['recipe_ingredients']['Row'];
export type RecipeTag                = Database['public']['Tables']['recipe_tags']['Row'];
export type UserIngredientPreference = Database['public']['Tables']['user_ingredient_preferences']['Row'];
export type UserFavoriteRecipe       = Database['public']['Tables']['user_favorite_recipes']['Row'];
export type Profile                  = Database['public']['Tables']['profiles']['Row'];
export type CurrentPrice             = Database['public']['Views']['current_prices']['Row'];
