import { synchronize } from '@nozbe/watermelondb/sync';
import { database } from '../db';
import { supabase } from './supabase';

const READ_ONLY_TABLES = [
  'stores', 'ingredients', 'store_products', 'prices',
  'ingredient_mappings', 'recipe_tags', 'flyers', 'flyer_items',
] as const;

const USER_TABLES = [
  'receipts', 'receipt_items', 'recipes', 'recipe_ingredients',
  'user_ingredient_preferences', 'user_favorite_recipes',
] as const;

const ALL_TABLES = [...READ_ONLY_TABLES, ...USER_TABLES] as const;
type TableName = typeof ALL_TABLES[number];

const toISO = (ts: number | null) =>
  ts ? new Date(ts).toISOString() : new Date(0).toISOString();

function mapRecord(table: TableName, row: Record<string, unknown>) {
  const base = {
    id: row.id as string,
    remote_id: row.id as string,
    updated_at: new Date(row.updated_at as string).getTime(),
  };
  const { id, created_at, ...rest } = row as any;
  return { ...base, ...rest };
}

async function pullChanges(lastPulledAt: number | null) {
  const since = toISO(lastPulledAt);
  const changes: Record<string, { created: unknown[]; updated: unknown[]; deleted: string[] }> = {};
  const { data: { user } } = await supabase.auth.getUser();
  const userId = user?.id;

  for (const table of ALL_TABLES) {
    let query = supabase.from(table).select('*').gt('updated_at', since);

    if ((USER_TABLES as readonly string[]).includes(table) && userId) {
      if (['receipts', 'receipt_items', 'user_ingredient_preferences', 'user_favorite_recipes'].includes(table)) {
        query = query.eq('user_id', userId);
      }
      if (table === 'recipes') {
        query = supabase.from('recipes').select('*').gt('updated_at', since)
          .or(`created_by.eq.${userId},is_public.eq.true`);
      }
    }

    const { data, error } = await query;
    if (error) { console.error(`[Sync] Pull error on ${table}:`, error.message); continue; }

    const created: unknown[] = [];
    const updated: unknown[] = [];
    const deleted: string[] = [];

    for (const row of (data ?? [])) {
      const mapped = mapRecord(table, row);
      if (row.deleted_at) { deleted.push(row.id as string); }
      else if (lastPulledAt === null || new Date(row.created_at).getTime() > lastPulledAt) { created.push(mapped); }
      else { updated.push(mapped); }
    }
    changes[table] = { created, updated, deleted };
  }
  return { changes, timestamp: Date.now() };
}

async function pushChanges(changes: Record<string, {
  created: Record<string, unknown>[];
  updated: Record<string, unknown>[];
  deleted: string[];
}>) {
  for (const [table, tableChanges] of Object.entries(changes)) {
    if ((READ_ONLY_TABLES as readonly string[]).includes(table)) continue;

    if (tableChanges.created.length > 0) {
      const rows = tableChanges.created.map(({ id, remote_id, ...rest }) => ({
        id: remote_id ?? id,
        ...rest,
        updated_at: new Date(rest.updated_at as number).toISOString(),
      }));
      const { error } = await supabase.from(table as any).upsert(rows, { onConflict: 'id' });
      if (error) console.error(`[Sync] Push create error on ${table}:`, error.message);
    }

    if (tableChanges.updated.length > 0) {
      const rows = tableChanges.updated.map(({ id, remote_id, ...rest }) => ({
        id: remote_id ?? id,
        ...rest,
        updated_at: new Date(rest.updated_at as number).toISOString(),
      }));
      const { error } = await supabase.from(table as any).upsert(rows, { onConflict: 'id' });
      if (error) console.error(`[Sync] Push update error on ${table}:`, error.message);
    }

    if (tableChanges.deleted.length > 0) {
      const { error } = await supabase.from(table as any)
        .update({ deleted_at: new Date().toISOString() })
        .in('id', tableChanges.deleted);
      if (error) console.error(`[Sync] Push delete error on ${table}:`, error.message);
    }
  }
}

export async function syncDatabase() {
  await synchronize({
    database,
    pullChanges: async ({ lastPulledAt }) => pullChanges(lastPulledAt),
    pushChanges: async ({ changes }) => pushChanges(changes as any),
    migrationsEnabledAtVersion: 1,
    sendCreatedAsUpdated: false,
  });
}
