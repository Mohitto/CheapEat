// @ts-nocheck
// TODO: nieużywane jeszcze — pakiet `react-native-onesignal` nie jest
// zainstalowany i ten moduł nie jest wpięty do App.tsx. Doinstaluj paczkę
// i podłącz initOneSignal() dopiero gdy powiadomienia push będą gotowe do testów
// (wymaga też natywnej konfiguracji Android/iOS pod OneSignal).
import OneSignal from 'react-native-onesignal';
import { supabase } from './supabase';

const ONESIGNAL_APP_ID = 'c4710f1e-a5bd-405e-8dc1-96e20c379996';

export function initOneSignal() {
  OneSignal.setAppId(ONESIGNAL_APP_ID);

  OneSignal.promptForPushNotificationsWithUserResponse((accepted) => {
    console.log('[OneSignal] Push accepted:', accepted);
    if (accepted) syncPlayerIdToSupabase();
  });

  OneSignal.setNotificationOpenedHandler((notification) => {
    console.log('[OneSignal] Opened:', notification);
    handleNotificationNavigation(notification);
  });

  OneSignal.setNotificationWillShowInForegroundHandler((event) => {
    event.complete(event.getNotification());
  });
}

export async function syncPlayerIdToSupabase() {
  try {
    const deviceState = await OneSignal.getDeviceState();
    if (!deviceState?.userId) return;

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    await supabase
      .from('profiles')
      .update({
        onesignal_player_id: deviceState.userId,
        push_enabled: deviceState.isPushDisabled === false,
      })
      .eq('id', user.id);

    console.log('[OneSignal] Player ID synced:', deviceState.userId);
  } catch (e) {
    console.warn('[OneSignal] Sync error:', e);
  }
}

export async function setOneSignalExternalUserId(userId: string) {
  OneSignal.setExternalUserId(userId, (results) => {
    console.log('[OneSignal] External user ID set:', results);
  });
}

function handleNotificationNavigation(notification: any) {
  const data = notification?.notification?.additionalData;
  if (!data) return;
  console.log('[OneSignal] Navigate to:', data);
}

export async function disablePush(userId: string) {
  OneSignal.disablePush(true);
  await supabase
    .from('profiles')
    .update({ push_enabled: false })
    .eq('id', userId);
}
