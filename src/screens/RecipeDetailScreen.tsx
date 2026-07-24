import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView,
  TouchableOpacity, ActivityIndicator, Alert,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { getRecipeById, calculateRecipeCost, type RecipeCostResult } from '../services/recipeService';
import { buildCartForRecipes } from '../services/cartService';
import Recipe from '../model/Recipe';

type Props = NativeStackScreenProps<RootStackParamList, 'RecipeDetail'>;

export function RecipeDetailScreen({ route }: Props) {
  const { recipeId } = route.params;
  const [recipe, setRecipe]   = useState<Recipe | null>(null);
  const [cost, setCost]       = useState<RecipeCostResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [addingToCart, setAddingToCart] = useState(false);

  useEffect(() => {
    (async () => {
      const [r, c] = await Promise.all([
        getRecipeById(recipeId),
        calculateRecipeCost(recipeId),
      ]);
      setRecipe(r);
      setCost(c);
      setLoading(false);
    })();
  }, [recipeId]);

  const handleAddToCart = async () => {
    setAddingToCart(true);
    try {
      await buildCartForRecipes([{ recipeId, portions: recipe?.portions ?? 1 }]);
      Alert.alert('Dodano do koszyka', 'Przejdź do zakładki Koszyk aby zobaczyć wyniki.');
    } catch (e) {
      Alert.alert('Błąd', 'Nie udało się dodać do koszyka.');
    } finally {
      setAddingToCart(false);
    }
  };

  if (loading) {
    return <View style={s.center}><ActivityIndicator size="large" color="#2ECC71" /></View>;
  }

  if (!recipe) {
    return <View style={s.center}><Text style={s.empty}>Przepis nie znaleziony.</Text></View>;
  }

  return (
    <ScrollView style={s.container} contentContainerStyle={{ paddingBottom: 40 }}>
      {/* Nagłówek */}
      <View style={s.heroBox}>
        <Text style={s.heroTitle}>{recipe.title}</Text>
        <View style={s.metaRow}>
          {recipe.prepMinutes != null && <Text style={s.metaChip}>⏱ {recipe.prepMinutes} min</Text>}
          {recipe.portions    != null && <Text style={s.metaChip}>🍽 {recipe.portions} porcji</Text>}
          {recipe.kcalPerPortion != null && <Text style={s.metaChip}>🔥 {recipe.kcalPerPortion} kcal</Text>}
        </View>
      </View>

      {/* Koszt */}
      {cost && (
        <View style={s.costBox}>
          <Text style={s.costLabel}>Szacowany koszt</Text>
          <Text style={s.costValue}>
            {cost.totalCostPln != null
              ? `${cost.totalCostPln.toFixed(2)} zł całość · ${cost.costPerPortionPln?.toFixed(2)} zł/porcję`
              : 'Brak danych cenowych'}
          </Text>
          {cost.missingPrices.length > 0 && (
            <Text style={s.missingText}>Brak cen: {cost.missingPrices.join(', ')}</Text>
          )}
        </View>
      )}

      {/* Składniki */}
      <Text style={s.sectionTitle}>Składniki</Text>
      {cost?.lines.map(line => (
        <View key={line.ingredientId} style={s.ingredientRow}>
          <Text style={s.ingredientName}>{line.ingredientName}</Text>
          <Text style={s.ingredientAmt}>{line.amount} {line.unit}</Text>
          <Text style={[s.ingredientCost, !line.costPln && s.noCost]}>
            {line.costPln != null ? `${line.costPln.toFixed(2)} zł` : '—'}
          </Text>
        </View>
      ))}

      {/* Przycisk koszyk */}
      <TouchableOpacity
        style={[s.btn, addingToCart && s.btnDisabled]}
        onPress={handleAddToCart}
        disabled={addingToCart}
        activeOpacity={0.8}
      >
        {addingToCart
          ? <ActivityIndicator color="#fff" />
          : <Text style={s.btnText}>🛒 Dodaj do koszyka</Text>
        }
      </TouchableOpacity>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#f5f5f5' },
  center:         { flex: 1, justifyContent: 'center', alignItems: 'center' },
  empty:          { color: '#999', fontSize: 15 },
  heroBox:        { backgroundColor: '#fff', padding: 20, paddingTop: 16, marginBottom: 12 },
  heroTitle:      { fontSize: 22, fontWeight: '700', color: '#111', marginBottom: 10 },
  metaRow:        { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  metaChip:       { backgroundColor: '#f0faf5', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4, fontSize: 13, color: '#2ECC71', fontWeight: '600' },
  costBox:        { backgroundColor: '#fff', padding: 16, marginBottom: 12 },
  costLabel:      { fontSize: 12, color: '#999', marginBottom: 4 },
  costValue:      { fontSize: 16, fontWeight: '700', color: '#111' },
  missingText:    { marginTop: 6, fontSize: 12, color: '#E74C3C' },
  sectionTitle:   { fontSize: 14, fontWeight: '700', color: '#555', paddingHorizontal: 16, paddingVertical: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  ingredientRow:  { backgroundColor: '#fff', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  ingredientName: { flex: 1, fontSize: 15, color: '#111' },
  ingredientAmt:  { fontSize: 14, color: '#666', marginRight: 12 },
  ingredientCost: { fontSize: 14, fontWeight: '600', color: '#2ECC71', minWidth: 52, textAlign: 'right' },
  noCost:         { color: '#ccc' },
  btn:            { margin: 16, backgroundColor: '#2ECC71', borderRadius: 14, paddingVertical: 16, alignItems: 'center' },
  btnDisabled:    { opacity: 0.6 },
  btnText:        { color: '#fff', fontSize: 16, fontWeight: '700' },
});
