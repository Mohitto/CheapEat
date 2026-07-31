import 'react-native-url-polyfill/auto';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import type { Database } from '../types/database.types';

const SUPABASE_URL = 'https://ncksaaafqovbrvjetlcc.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5ja3NhYWFmcW92YnJ2amV0bGNjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYzMjc5MjcsImV4cCI6MjA5MTkwMzkyN30.qx_4eZuIf8xe9d5qeC5qhQjnvF8NdT9pBOuRYLgujls';

export const supabase = createClient<Database>(SUPABASE_URL, SUPABASE_KEY, {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

// Typy pomocniczo
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
