import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
  TextInput, Image, Linking,
} from 'react-native';

type Recipe = {
  id: string;
  title: string;
  image: string;
  url: string;
  category: string;
};

async function fetchAniaRecipes(query: string = ''): Promise<Recipe[]> {
  try {
    const searchUrl = query
      ? `https://aniagotuje.pl/?s=${encodeURIComponent(query)}`
      : 'https://aniagotuje.pl/';

    const res = await fetch(searchUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Android)' },
    });
    const html = await res.text();

    const recipes: Recipe[] = [];
    // Parsowanie kart przepisów z HTML
    const articleRegex = /<article[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)<\/article>/gs;
    const titleRegex = /<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/s;
    const imgRegex = /<img[^>]*src="([^"]+)"[^>]*>/;
    const catRegex = /<a[^>]*rel="category tag"[^>]*>([^<]+)<\/a>/;

    let match;
    while ((match = articleRegex.exec(html)) !== null && recipes.length < 20) {
      const block = match[1];
      const titleMatch = titleRegex.exec(block);
      const imgMatch = imgRegex.exec(block);
      const catMatch = catRegex.exec(block);

      if (titleMatch) {
        recipes.push({
          id: titleMatch[1],
          title: titleMatch[2].trim(),
          image: imgMatch ? imgMatch[1] : '',
          url: titleMatch[1],
          category: catMatch ? catMatch[1].trim() : '',
        });
      }
    }
    return recipes;
  } catch (e) {
    console.error('[FeedScreen] fetch error', e);
    return [];
  }
}

export function FeedScreen() {
  const [recipes, setRecipes]     = useState<Recipe[]>([]);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery]         = useState('');

  const load = useCallback(async (q: string = '') => {
    setLoading(true);
    const data = await fetchAniaRecipes(q);
    setRecipes(data);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load(query);
    setRefreshing(false);
  };

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
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2ECC71" />}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={s.card}
              onPress={() => Linking.openURL(item.url)}
              activeOpacity={0.75}
            >
              {item.image ? (
                <Image source={{ uri: item.image }} style={s.img} resizeMode="cover" />
              ) : null}
              <View style={s.cardBody}>
                {item.category ? <Text style={s.cat}>{item.category}</Text> : null}
                <Text style={s.title}>{item.title}</Text>
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
  container:   { flex: 1, backgroundColor: '#f5f5f5' },
  center:      { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingText: { color: '#999', fontSize: 14 },
  headerBox:   { backgroundColor: '#fff', paddingTop: 52, paddingHorizontal: 16, paddingBottom: 12 },
  header:      { fontSize: 24, fontWeight: '700', marginBottom: 10, color: '#111' },
  search:      { backgroundColor: '#f0f0f0', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 9, fontSize: 15, color: '#111' },
  list:        { padding: 12, paddingBottom: 24 },
  card:        { backgroundColor: '#fff', borderRadius: 12, marginBottom: 12, overflow: 'hidden', elevation: 2 },
  img:         { width: '100%', height: 160 },
  cardBody:    { padding: 12 },
  cat:         { fontSize: 12, color: '#2ECC71', fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' },
  title:       { fontSize: 16, fontWeight: '600', color: '#111' },
  empty:       { textAlign: 'center', marginTop: 60, color: '#999', fontSize: 15, lineHeight: 24 },
});
