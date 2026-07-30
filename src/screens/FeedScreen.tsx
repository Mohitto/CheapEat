import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
  TextInput, Image, Linking,
} from 'react-native';

const EDGE_URL = 'https://ncksaaafqovbrvjetlcc.supabase.co/functions/v1/scrape-recipes';

type RecipeItem = {
  id: string;
  title: string;
  url: string;
  image: string;
  category: string;
  source: string;
};

async function fetchRecipes(query: string = ''): Promise<RecipeItem[]> {
  try {
    const url = query ? `${EDGE_URL}?q=${encodeURIComponent(query)}` : EDGE_URL;
    const res = await fetch(url);
    const json = await res.json();
    return json.recipes ?? [];
  } catch (e) {
    console.error('[FeedScreen]', e);
    return [];
  }
}

export function FeedScreen() {
  const [recipes, setRecipes]       = useState<RecipeItem[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery]           = useState('');

  const load = useCallback(async (q: string = '') => {
    setLoading(true);
    const data = await fetchRecipes(q);
    setRecipes(data);
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
              onRefresh={async () => { setRefreshing(true); await load(query); setRefreshing(false); }}
              tintColor="#2ECC71"
            />
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              style={s.card}
              onPress={() => Linking.openURL(item.url)}
              activeOpacity={0.75}
            >
              {item.image ? (
                <Image source={{ uri: item.image }} style={s.img} resizeMode="cover" />
              ) : (
                <View style={[s.img, s.imgPlaceholder]}>
                  <Text style={{ fontSize: 32 }}>🍽</Text>
                </View>
              )}
              <View style={s.cardBody}>
                {item.category ? <Text style={s.cat}>{item.category}</Text> : null}
                <Text style={s.title}>{item.title}</Text>
                <Text style={s.source}>aniagotuje.pl</Text>
              </View>
            </TouchableOpacity>
          )}
          contentContainerStyle={s.list}
          ListEmptyComponent={
            <Text style={s.empty}>Nie znaleziono przepisów.{`\n`}Spróbuj innej frazy.</Text>
          }
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#f5f5f5' },
  center:         { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingText:    { color: '#999', fontSize: 14 },
  headerBox:      { backgroundColor: '#fff', paddingTop: 52, paddingHorizontal: 16, paddingBottom: 12 },
  header:         { fontSize: 24, fontWeight: '700', marginBottom: 10, color: '#111' },
  search:         { backgroundColor: '#f0f0f0', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 9, fontSize: 15, color: '#111' },
  list:           { padding: 12, paddingBottom: 24 },
  card:           { backgroundColor: '#fff', borderRadius: 12, marginBottom: 12, overflow: 'hidden', elevation: 2 },
  img:            { width: '100%', height: 180 },
  imgPlaceholder: { justifyContent: 'center', alignItems: 'center', backgroundColor: '#f0f0f0' },
  cardBody:       { padding: 12 },
  cat:            { fontSize: 12, color: '#2ECC71', fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' },
  title:          { fontSize: 16, fontWeight: '600', color: '#111', marginBottom: 4 },
  source:         { fontSize: 12, color: '#aaa' },
  empty:          { textAlign: 'center', marginTop: 60, color: '#999', fontSize: 15, lineHeight: 24 },
});
