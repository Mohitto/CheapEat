import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, Alert,
} from 'react-native';
import {
  getUserPreferences,
  setIngredientPreference,
  clearIngredientPreference,
  type IngredientPreferenceRow,
} from '../services/userService';
import { supabase } from '../lib/supabase';

const PREF_OPTIONS = [
  { value: 'like',    label: '👍 Lubię',   color: '#2ECC71' },
  { value: 'dislike', label: '👎 Nie lubię', color: '#E74C3C' },
  { value: 'allergy', label: '🚫 Alergia', color: '#E67E22' },
];

export function PreferencesScreen() {
  const [prefs, setPrefs]     = useState<IngredientPreferenceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId]   = useState<string | null>(null);

  const loadPrefs = useCallback(async (uid: string) => {
    try {
      const data = await getUserPreferences(uid);
      setPrefs(data);
    } catch (e) {
      console.error('[PreferencesScreen]', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setUserId(user.id);
        loadPrefs(user.id);
      } else {
        setLoading(false);
      }
    });
  }, [loadPrefs]);

  const handleSet = async (ingredientId: string, preference: string) => {
    if (!userId) { Alert.alert('Musisz być zalogowany'); return; }
    try {
      await setIngredientPreference(userId, ingredientId, preference as any);
      await loadPrefs(userId);
    } catch (e) {
      Alert.alert('Błąd', String(e));
    }
  };

  const handleClear = async (ingredientId: string) => {
    if (!userId) return;
    try {
      await clearIngredientPreference(userId, ingredientId);
      await loadPrefs(userId);
    } catch (e) {
      Alert.alert('Błąd', String(e));
    }
  };

  if (loading) {
    return <View style={s.center}><ActivityIndicator size="large" color="#2ECC71" /></View>;
  }

  if (!userId) {
    return (
      <View style={s.center}>
        <Text style={s.emptyTitle}>Nie jesteś zalogowany</Text>
        <Text style={s.emptySubtitle}>Zaloguj się, żeby zarządzać preferencjami składników.</Text>
      </View>
    );
  }

  return (
    <View style={s.container}>
      <Text style={s.header}>Preferencje</Text>
      <FlatList
        data={prefs}
        keyExtractor={item => item.ingredientId}
        renderItem={({ item }) => (
          <View style={s.card}>
            <Text style={s.ingName}>{item.ingredientName ?? item.ingredientId}</Text>
            <View style={s.row}>
              {PREF_OPTIONS.map(opt => (
                <TouchableOpacity
                  key={opt.value}
                  style={[
                    s.prefBtn,
                    item.preference === opt.value && { backgroundColor: opt.color, borderColor: opt.color },
                  ]}
                  onPress={() =>
                    item.preference === opt.value
                      ? handleClear(item.ingredientId)
                      : handleSet(item.ingredientId, opt.value)
                  }
                  activeOpacity={0.75}
                >
                  <Text style={[
                    s.prefBtnText,
                    item.preference === opt.value && { color: '#fff' },
                  ]}>
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}
        contentContainerStyle={{ padding: 12, paddingBottom: 24 }}
        ListEmptyComponent={
          <View style={s.emptyBox}>
            <Text style={s.emptyTitle}>Brak składników</Text>
            <Text style={s.emptySubtitle}>Preferencje pojawią się po załadowaniu składników z bazy.</Text>
          </View>
        }
      />
    </View>
  );
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#f5f5f5' },
  center:       { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  header:       { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff' },
  card:         { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 8, elevation: 1 },
  ingName:      { fontSize: 15, fontWeight: '600', color: '#111', marginBottom: 10 },
  row:          { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  prefBtn:      { borderRadius: 8, borderWidth: 1.5, borderColor: '#ddd', paddingHorizontal: 12, paddingVertical: 6 },
  prefBtnText:  { fontSize: 13, color: '#555' },
  emptyBox:     { marginTop: 60, alignItems: 'center', paddingHorizontal: 32 },
  emptyTitle:   { fontSize: 17, fontWeight: '700', color: '#333', marginBottom: 8 },
  emptySubtitle:{ fontSize: 14, color: '#999', textAlign: 'center', lineHeight: 20 },
});
