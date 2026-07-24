import { supabase } from '../lib/supabase';
import database from '../model/database';
import { Q } from '@nozbe/watermelondb';
import UserIngredientPreference from '../model/UserIngredientPreference';
import UserFavoriteRecipe from '../model/UserFavoriteRecipe';

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export type UserProfile = {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
  is_anonymous: boolean;
  push_enabled: boolean;
  onesignal_player_id: string | null;
  platform: string | null;
  app_version: string | null;
};

/**
 * Pobiera profil aktualnie zalogowanego użytkownika z Supabase.
 */
export async function getMyProfile(): Promise<UserProfile | null> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from('profiles')
    .select('id, display_name, avatar_url, is_anonymous, push_enabled, onesignal_player_id, platform, app_version')
    .eq('id', user.id)
    .single();

  if (error) throw error;
  return data;
}

/**
 * Aktualizuje wybrane pola profilu.
 */
export async function updateMyProfile(
  fields: Partial<Pick<UserProfile, 'display_name' | 'avatar_url' | 'push_enabled' | 'onesignal_player_id' | 'platform' | 'app_version'>>
): Promise<void> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) throw new Error('Brak zalogowanego użytkownika');

  const { error } = await supabase
    .from('profiles')
    .update({ ...fields, updated_at: new Date().toISOString() })
    .eq('id', user.id);

  if (error) throw error;
}

// ---------------------------------------------------------------------------
// Preferencje składników (lokalne — WatermelonDB)
// ---------------------------------------------------------------------------

export type PreferenceType = 'like' | 'dislike' | 'allergy';

/**
 * Zwraca preferencje użytkownika dla wszystkich składników.
 */
export async function getIngredientPreferences(
  userId: string
): Promise<UserIngredientPreference[]> {
  return database
    .get<UserIngredientPreference>('user_ingredient_preferences')
    .query(Q.where('user_id', userId))
    .fetch();
}

/**
 * Ustawia preferencję dla składnika. Jeśli już istnieje — nadpisuje.
 */
export async function setIngredientPreference(
  userId: string,
  ingredientId: string,
  preference: PreferenceType
): Promise<void> {
  await database.write(async () => {
    const existing = await database
      .get<UserIngredientPreference>('user_ingredient_preferences')
      .query(
        Q.where('user_id', userId),
        Q.where('ingredient_id', ingredientId)
      )
      .fetch();

    if (existing.length > 0) {
      await existing[0].update(record => {
        (record as any).preference = preference;
      });
    } else {
      await database
        .get<UserIngredientPreference>('user_ingredient_preferences')
        .create(record => {
          (record as any).userId = userId;
          (record as any).ingredientId = ingredientId;
          (record as any).preference = preference;
        });
    }
  });
}

/**
 * Usuwa preferencję dla składnika.
 */
export async function removeIngredientPreference(
  userId: string,
  ingredientId: string
): Promise<void> {
  await database.write(async () => {
    const existing = await database
      .get<UserIngredientPreference>('user_ingredient_preferences')
      .query(
        Q.where('user_id', userId),
        Q.where('ingredient_id', ingredientId)
      )
      .fetch();

    if (existing.length > 0) {
      await existing[0].destroyPermanently();
    }
  });
}

// ---------------------------------------------------------------------------
// Ulubione przepisy (lokalne — WatermelonDB)
// ---------------------------------------------------------------------------

/**
 * Zwraca listę ulubionych przepisów użytkownika.
 */
export async function getFavoriteRecipes(
  userId: string
): Promise<UserFavoriteRecipe[]> {
  return database
    .get<UserFavoriteRecipe>('user_favorite_recipes')
    .query(Q.where('user_id', userId))
    .fetch();
}

/**
 * Dodaje przepis do ulubionych. Idempotentne — nie duplikuje.
 */
export async function addFavoriteRecipe(
  userId: string,
  recipeId: string
): Promise<void> {
  await database.write(async () => {
    const existing = await database
      .get<UserFavoriteRecipe>('user_favorite_recipes')
      .query(
        Q.where('user_id', userId),
        Q.where('recipe_id', recipeId)
      )
      .fetch();

    if (existing.length === 0) {
      await database
        .get<UserFavoriteRecipe>('user_favorite_recipes')
        .create(record => {
          (record as any).userId = userId;
          (record as any).recipeId = recipeId;
        });
    }
  });
}

/**
 * Usuwa przepis z ulubionych.
 */
export async function removeFavoriteRecipe(
  userId: string,
  recipeId: string
): Promise<void> {
  await database.write(async () => {
    const existing = await database
      .get<UserFavoriteRecipe>('user_favorite_recipes')
      .query(
        Q.where('user_id', userId),
        Q.where('recipe_id', recipeId)
      )
      .fetch();

    if (existing.length > 0) {
      await existing[0].destroyPermanently();
    }
  });
}

/**
 * Sprawdza czy przepis jest w ulubionych.
 */
export async function isFavoriteRecipe(
  userId: string,
  recipeId: string
): Promise<boolean> {
  const results = await database
    .get<UserFavoriteRecipe>('user_favorite_recipes')
    .query(
      Q.where('user_id', userId),
      Q.where('recipe_id', recipeId)
    )
    .fetch();
  return results.length > 0;
}
