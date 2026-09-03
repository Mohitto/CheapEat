import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
  TextInput, Image,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { Recipe } from '../model/Recipe';
import { getFeedRecipes, calculateRecipeCost, type RecipeCostResult } from '../services/recipeService';
import { syncDatabase } from '../lib/sync';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export function FeedScreen() {
  const navigation = useNavigation<Nav>();
  const [recipes, setRecipes]       = useState<Recipe[]>([]);
  const [costs, setCosts]           = useState<Record<string, RecipeCostResult | null>>({});
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery]           = useState('');

  const load = useCallback(async (q: string = '') => {
    setLoading(true);
    const data = await getFeedRecipes(q);
    setRecipes(data);
    setLoading(false);

    // Koszt liczymy w tle, per przepis — karta pokazuje spinner ceny do czasu policzenia
    const results = await Promise.all(
      data.map(async r => [r.id, await calculateRecipeCost(r.id)] as const)
    );
    setCosts(Object.fromEntries(results));
  }, []);

  useFocusEffect(useCallback(() => { load(query); }, [load, query]));

  const onRefresh = async () => {
    setRefreshing(true);
    try { await syncDatabase(); } catch (e) { console.warn('[FeedScreen] sync error:', e); }
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
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2ECC71" />
          }
          renderItem={({ item }) => {
            const cost = costs[item.id];
            return (
              <TouchableOpacity
                style={s.card}
                onPress={() => navigation.navigate('RecipeDetail', { recipeId: item.id })}
                activeOpacity={0.75}
              >
                {item.imageUrl ? (
                  <Image source={{ uri: item.imageUrl }} style={s.img} resizeMode="cover" />
                ) : (
                  <View style={[s.img, s.imgPlaceholder]}>
                    <Text style={s.imgPlaceholderEmoji}>🍽️</Text>
                  </View>
                )}
                <View style={s.cardBody}>
                  {item.category ? <Text style={s.cat}>{item.category}</Text> : null}
                  <Text style={s.title}>{item.title}</Text>

                  <View style={s.priceRow}>
                    {cost === undefined ? (
                      <ActivityIndicator size="small" color="#2ECC71" />
                    ) : cost?.totalCostPln != null ? (
                      <>
                        <Text style={s.price}>{cost.totalCostPln.toFixed(2)} zł</Text>
                        {cost.costPerPortionPln != null && (
                          <Text style={s.pricePerPortion}> · {cost.costPerPortionPln.toFixed(2)} zł/porcję</Text>
                        )}
                      </>
                    ) : (
                      <Text style={s.noPrice}>brak cen</Text>
                    )}
                  </View>
                </View>
              </TouchableOpacity>
            );
          }}
          contentContainerStyle={recipes.length === 0 ? s.centerFlex : s.list}
          ListEmptyComponent={
            <Text style={s.emptyText}>
              {`Brak przepisów w bazie.\nPrzeciągnij w dół żeby odświeżyć.`}
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
  imgPlaceholderEmoji: { fontSize: 36 },
  cardBody:     { padding: 12 },
  cat:          { fontSize: 12, color: '#2ECC71', fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' },
  title:        { fontSize: 16, fontWeight: '600', color: '#111', marginBottom: 6 },
  priceRow:     { flexDirection: 'row', alignItems: 'center', minHeight: 20 },
  price:        { fontSize: 15, fontWeight: '700', color: '#2ECC71' },
  pricePerPortion: { fontSize: 13, color: '#888' },
  noPrice:      { fontSize: 13, color: '#ccc', fontStyle: 'italic' },
  emptyText:    { textAlign: 'center', color: '#999', fontSize: 15, lineHeight: 24 },
});
