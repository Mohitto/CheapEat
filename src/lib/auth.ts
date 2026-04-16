import { supabase } from './supabase';
import { syncDatabase } from './sync';

export type AuthSession = Awaited<ReturnType<typeof supabase.auth.getSession>>['data']['session'];

export async function signInAnonymously() {
  const { data, error } = await supabase.auth.signInAnonymously();
  if (error) throw error;
  return data.session;
}

export async function signInWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: 'cheapeat://auth/callback' },
  });
  if (error) throw error;
  return data;
}

export async function signUpWithEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) throw error;
  return data.session;
}

export async function signInWithEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data.session;
}

// Link anonimowego konta z e-mail — ten sam user_id, zero utraty danych
export async function linkAnonToEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.updateUser({ email, password });
  if (error) throw error;

  const { data: { user } } = await supabase.auth.getUser();
  if (user) {
    await supabase
      .from('profiles')
      .update({ is_anonymous: false, linked_at: new Date().toISOString() })
      .eq('id', user.id);
  }
  return data;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function ensureSession(): Promise<AuthSession> {
  const { data: { session } } = await supabase.auth.getSession();
  if (session) return session;
  return await signInAnonymously();
}

export function onAuthStateChange(
  callback: (event: string, session: AuthSession) => void
) {
  return supabase.auth.onAuthStateChange(async (event, session) => {
    callback(event, session);
    if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
      try { await syncDatabase(); }
      catch (e) { console.warn('[Auth] Sync po logowaniu nie powiodło się:', e); }
    }
  });
}
