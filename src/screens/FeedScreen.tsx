import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { getPublicRecipes } from '../services/recipeService';
import { calculateRecipeCost } from '../services/recipeService';
import type { RootStackParamList } from '../navigation/types';
import Recipe from '../model/Recipe';

type Nav = NativeStackNavigationProp<RootStackParamList>;

type RecipeRow = {
  recipe: Recipe;
  costPerPortion: number | null;
  loading: boolean;
};

export function FeedScreen() {
  const nav = useNavigation<Nav>();
  const [rows, setRows]         = useState<RecipeRow[]>([]);
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const recipes = await getPublicRecipes();
      // Pokaż listę od razu, ceny ładuj asynchronicznie
      setRows(recipes.map(r => ({ recipe: r, costPerPortion: null, loading: true })));
      setLoading(false);

      // Ładuj ceny po jednej
      for (const recipe of recipes) {
        calculateRecipeCost(recipe.id).then(result => {
          setRows(prev => prev.map(row =>
            row.recipe.id === recipe.id
              ? { ...row, costPerPortion: result?.costPerPortionPln ?? null, loading: false }
              : row
          ));
        });
      }
    } catch (e) {
      console.error('[FeedScreen]', e);
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (loading) {
    return <View style={s.center}><ActivityIndicator size="large" color="#2ECC71" /></View>;
  }

  return (
    <View style={s.container}>
      <Text style={s.header}>Przepisy</Text>
      <FlatList
        data={rows}
        keyExtractor={item => item.recipe.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2ECC71" />}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={s.card}
            onPress={() => nav.navigate('RecipeDetail', { recipeId: item.recipe.id })}
            activeOpacity={0.75}
          >
            <Text style={s.title}>{item.recipe.title}</Text>
            <View style={s.row}>
              {item.recipe.proteinPerPortion != null && (
                <Text style={s.meta}>🥩 {item.recipe.proteinPerPortion}g</Text>
              )}
              {item.recipe.prepMinutes != null && (
                <Text style={s.meta}>⏱ {item.recipe.prepMinutes} min</Text>
              )}
              <View style={s.priceBox}>
                {item.loading
                  ? <ActivityIndicator size="small" color="#2ECC71" />
                  : <Text style={s.price}>
                      {item.costPerPortion != null
                        ? `${item.costPerPortion.toFixed(2)} zł/porcję`
                        : 'brak ceny'}
                    </Text>
                }
              </View>
            </View>
          </TouchableOpacity>
        )}
        contentContainerStyle={s.list}
        ListEmptyComponent={
          <Text style={s.empty}>Brak przepisów. Dodaj dane do bazy.</Text>
        }
      />
    </View>
  );
}

const s = StyleSheet.create({
  container:  { flex: 1, backgroundColor: '#f5f5f5' },
  center:     { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header:     { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff' },
  list:       { padding: 12, paddingBottom: 24 },
  card:       { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12, elevation: 2, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 8 },
  title:      { fontSize: 16, fontWeight: '600', marginBottom: 8, color: '#111' },
  row:        { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meta:       { fontSize: 13, color: '#666' },
  priceBox:   { marginLeft: 'auto', minWidth: 80, alignItems: 'flex-end' },
  price:      { fontSize: 14, fontWeight: '700', color: '#2ECC71' },
  empty:      { textAlign: 'center', marginTop: 60, color: '#999', fontSize: 15 },
});
