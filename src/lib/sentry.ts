import * as Sentry from '@sentry/react-native';
import { supabase } from './supabase';

const SENTRY_DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? '';

export function initSentry() {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: __DEV__ ? 'development' : 'production',
    tracesSampleRate: __DEV__ ? 1.0 : 0.2,
    attachStacktrace: true,
    enabled: !__DEV__,
  });
}

export async function setSentryUser() {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;
  Sentry.setUser({
    id: user.id,
    email: user.email ?? 'anonymous',
    username: user.user_metadata?.display_name ?? 'anon',
  });
}

export function clearSentryUser() {
  Sentry.setUser(null);
}

export async function captureError(
  error: unknown,
  context?: Record<string, unknown>,
  saveToDb = false
) {
  const sentryId = Sentry.captureException(error, { extra: context });

  if (saveToDb) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        await supabase.from('error_logs').insert({
          user_id: user.id,
          sentry_id: sentryId,
          level: 'error',
          message: error instanceof Error ? error.message : String(error),
          context,
        });
      }
    } catch (dbErr) {
      console.warn('[Sentry] DB log failed:', dbErr);
    }
  }
  return sentryId;
}

export function addBreadcrumb(message: string, data?: Record<string, unknown>) {
  Sentry.addBreadcrumb({
    message,
    data,
    level: 'info',
    timestamp: Date.now() / 1000,
  });
}
