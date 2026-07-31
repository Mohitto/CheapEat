import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
  TextInput, Image,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { supabase } from '../lib/supabase';

type Nav = NativeStackNavigationProp<RootStackParamList>;

type RecipeRow = {
  id: string;
  title: string;
  source_url: string | null;
  image_url: string | null;
  category: string | null;
  source: string | null;
};

async function fetchRecipes(query: string = ''): Promise<RecipeRow[]> {
  let q = supabase
    .from('recipes')
    .select('id, title, source_url, image_url, category, source')
    .eq('is_public', true)
    .is('deleted_at', null)
    .order('scraped_at', { ascending: false })
    .limit(50);

  if (query.trim()) {
    q = q.ilike('title', `%${query.trim()}%`);
  }

  const { data, error } = await q;
  if (error) { console.error('[FeedScreen]', error); return []; }
  return (data as RecipeRow[]) ?? [];
}

export function FeedScreen() {
  const navigation = useNavigation<Nav>();
  const [recipes, setRecipes]       = useState<RecipeRow[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery]           = useState('');
  const [empty, setEmpty]           = useState(false);

  const load = useCallback(async (q: string = '') => {
    setLoading(true);
    const data = await fetchRecipes(q);
    setRecipes(data);
    setEmpty(data.length === 0);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={s.container}>
      <View style={s.headerBox}>
        <Text style={s.header}>Przepisy</Text>
        <TextInput
          style={s.search}
          placeholder="Szukaj przepisu..."
          placeholderTextColor="#aaa"
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={() => load(query)}
          returnKeyType="search"
        />
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color="#2ECC71" />
          <Text style={s.loadingText}>Ładowanie przepisów...</Text>
        </View>
      ) : (
        <FlatList
          data={recipes}
          keyExtractor={item => item.id}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load(query);
                setRefreshing(false);
              }}
              tintColor="#2ECC71"
            />
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              style={s.card}
              onPress={() => navigation.navigate('RecipeDetail', { recipeId: item.id })}
              activeOpacity={0.75}
            >
              {item.image_url ? (
                <Image source={{ uri: item.image_url }} style={s.img} resizeMode="cover" />
              ) : (
                <View style={[s.img, s.imgPlaceholder]}>
                  <Text style={{ fontSize: 36 }}>🍽️</Text>
                </View>
              )}
              <View style={s.cardBody}>
                {item.category ? <Text style={s.cat}>{item.category}</Text> : null}
                <Text style={s.title}>{item.title}</Text>
                <Text style={s.source}>{item.source ?? 'aniagotuje.pl'}</Text>
              </View>
            </TouchableOpacity>
          )}
          contentContainerStyle={recipes.length === 0 ? s.centerFlex : s.list}
          ListEmptyComponent={
            <Text style={s.emptyText}>
              {empty
                ? `Brak przepisów w bazie.\nNaciśnij odśwież lub poczekaj na import.`
                : 'Nie znaleziono przepisów dla tej frazy.'}
            </Text>
          }
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#f5f5f5' },
  center:       { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  centerFlex:   { flexGrow: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText:  { color: '#999', fontSize: 14 },
  headerBox:    { backgroundColor: '#fff', paddingTop: 52, paddingHorizontal: 16, paddingBottom: 12 },
  header:       { fontSize: 24, fontWeight: '700', marginBottom: 10, color: '#111' },
  search:       { backgroundColor: '#f0f0f0', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 9, fontSize: 15, color: '#111' },
  list:         { padding: 12, paddingBottom: 24 },
  card:         { backgroundColor: '#fff', borderRadius: 12, marginBottom: 12, overflow: 'hidden', elevation: 2 },
  img:          { width: '100%', height: 180 },
  imgPlaceholder: { justifyContent: 'center', alignItems: 'center', backgroundColor: '#f0f0f0' },
  cardBody:     { padding: 12 },
  cat:          { fontSize: 12, color: '#2ECC71', fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' },
  title:        { fontSize: 16, fontWeight: '600', color: '#111', marginBottom: 4 },
  source:       { fontSize: 12, color: '#aaa' },
  emptyText:    { textAlign: 'center', color: '#999', fontSize: 15, lineHeight: 24 },
});
