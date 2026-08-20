import React, { useEffect, useState } from 'react';
import { StatusBar, View, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { RootNavigator } from './src/navigation/RootNavigator';
import { ensureSession } from './src/lib/auth';
import { syncDatabase } from './src/lib/sync';

export default function App() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        await ensureSession();
        await syncDatabase();
      } catch (e) {
        // Brak sieci / błąd sync nie powinien blokować wejścia do apki —
        // Feed i tak czyta przepisy bezpośrednio z Supabase.
        console.warn('[App] Bootstrap (sesja/sync) nie powiódł się:', e);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  if (!ready) {
    return (
      <SafeAreaProvider>
        <View style={s.loading}>
          <ActivityIndicator size="large" color="#2ECC71" />
        </View>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" backgroundColor="#fff" />
      <NavigationContainer>
        <RootNavigator />
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  loading: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fff' },
});
