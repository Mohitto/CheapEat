import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView,
  TouchableOpacity, ActivityIndicator, Alert,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import {
  getRecipeById, calculateRecipeCost,
  type RecipeCostResult, type ShoppingPlan, type IngredientCostLine,
} from '../services/recipeService';
import { buildCartForRecipes } from '../services/cartService';
import { Recipe } from '../model/Recipe';

type Props = NativeStackScreenProps<RootStackParamList, 'RecipeDetail'>;

/** "2026-09-12" -> "12.09" — na gazetce daty są w tej formie. */
function shortDate(iso: string): string {
  const [, month, day] = iso.split('-');
  return `${day}.${month}`;
}

/**
 * Co konkretnie trzeba włożyć do koszyka.
 *
 * Produkty na wagę scraper zapisuje jako opakowanie 1 g (kupujesz
 * dokładnie tyle, ile trzeba), więc dosłowne "kup 300× opak. (1g)"
 * byłoby prawdziwe, ale bez sensu do przeczytania.
 */
function packageLabel(line: IngredientCostLine): string | null {
  if (line.packagesNeeded == null || line.unitAmount == null) return null;
  if (line.unitAmount === 1 && line.unit !== 'szt') {
    return `${line.packagesNeeded}${line.unit} na wagę`;
  }
  const size = `${line.unitAmount % 1 === 0 ? line.unitAmount : line.unitAmount.toFixed(1)}${line.unit}`;
  return `kup ${line.packagesNeeded}× ${size}`;
}

export function RecipeDetailScreen({ route }: Props) {
  const { recipeId } = route.params;
  const [recipe, setRecipe]   = useState<Recipe | null>(null);
  const [cost, setCost]       = useState<RecipeCostResult | null>(null);
  const [plan, setPlan]       = useState<ShoppingPlan['kind']>('cheapest-basket');
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
    } catch {
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

  // Dwie odpowiedzi na "ile to kosztuje": najtaniej w ogóle (objazd
  // kilku sklepów) i najtaniej w jednym sklepie. Pokazujemy obie, bo
  // sama ta pierwsza obiecuje cenę, której w praktyce nikt nie zapłaci.
  const basket = cost?.cheapestBasket ?? null;
  const single = cost?.singleStore ?? null;
  const shown  = (plan === 'single-store' ? single : basket) ?? basket;

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

      {/* Dwie opcje zakupów */}
      {basket && (
        <View style={s.planRow}>
          <TouchableOpacity
            style={[s.planCard, plan === 'cheapest-basket' && s.planCardActive]}
            onPress={() => setPlan('cheapest-basket')}
            activeOpacity={0.85}
          >
            <Text style={s.planLabel}>Najtańsze zakupy</Text>
            <Text style={s.planPrice}>
              {basket.totalCostPln != null ? `${basket.totalCostPln.toFixed(2)} zł` : '—'}
            </Text>
            <Text style={s.planMeta}>
              {basket.storeNames.length > 0 ? basket.storeNames.join(' + ') : 'brak cen'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[s.planCard, plan === 'single-store' && s.planCardActive, !single && s.planCardOff]}
            onPress={() => single && setPlan('single-store')}
            activeOpacity={single ? 0.85 : 1}
            disabled={!single}
          >
            <Text style={s.planLabel}>Jeden sklep</Text>
            <Text style={s.planPrice}>
              {single?.totalCostPln != null ? `${single.totalCostPln.toFixed(2)} zł` : '—'}
            </Text>
            <Text style={s.planMeta}>
              {single?.storeNames.join(' + ') || 'brak pełnej oferty'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {cost?.multiStoreSavingsPln != null && cost.multiStoreSavingsPln > 0 && (
        <Text style={s.savings}>
          Objazd dwóch sklepów oszczędza {cost.multiStoreSavingsPln.toFixed(2)} zł.
        </Text>
      )}

      {shown && (
        <View style={s.costBox}>
          <Text style={s.costLabel}>
            {shown.kind === 'single-store' ? 'Wszystko w jednym sklepie' : 'Każdy składnik z najtańszego sklepu'}
          </Text>
          <Text style={s.costValue}>
            {shown.totalCostPln != null
              ? `${shown.totalCostPln.toFixed(2)} zł całość · ${shown.costPerPortionPln?.toFixed(2)} zł/porcję`
              : 'Brak danych cenowych'}
          </Text>
          {shown.missingPrices.length > 0 && (
            <Text style={s.missingText}>Brak cen: {shown.missingPrices.join(', ')}</Text>
          )}
        </View>
      )}

      {/* Składniki */}
      <Text style={s.sectionTitle}>Składniki</Text>
      {shown?.lines.map(line => (
        <View key={line.ingredientId} style={s.ingredientRow}>
          <View style={{ flex: 1 }}>
            <View style={s.nameRow}>
              <Text style={s.ingredientName}>{line.ingredientName}</Text>
              {line.isPromo && <Text style={s.promoTag}>promocja</Text>}
            </View>
            {line.storeName && (
              <Text style={s.ingredientStore}>
                {[line.storeName, packageLabel(line)].filter(Boolean).join(' · ')}
                {line.promoEndsOn && ` · do ${shortDate(line.promoEndsOn)}`}
              </Text>
            )}
            {line.upcoming && (
              <Text style={s.upcoming}>
                od {shortDate(line.upcoming.startsOn)}: {line.upcoming.grossPricePln.toFixed(2)} zł
              </Text>
            )}
          </View>
          <Text style={s.ingredientAmt}>{line.amount} {line.unit}</Text>
          <View style={s.costCol}>
            {line.regularPricePln != null && line.packagesNeeded != null && (
              <Text style={s.wasPrice}>
                {(line.regularPricePln * line.packagesNeeded).toFixed(2)} zł
              </Text>
            )}
            <Text style={[s.ingredientCost, !line.costPln && s.noCost]}>
              {line.costPln != null ? `${line.costPln.toFixed(2)} zł` : '—'}
            </Text>
          </View>
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
  planRow:        { flexDirection: 'row', gap: 10, paddingHorizontal: 16, marginBottom: 10 },
  planCard:       { flex: 1, backgroundColor: '#fff', borderRadius: 14, padding: 14, borderWidth: 2, borderColor: 'transparent' },
  planCardActive: { borderColor: '#2ECC71' },
  planCardOff:    { opacity: 0.5 },
  planLabel:      { fontSize: 12, color: '#999' },
  planPrice:      { fontSize: 20, fontWeight: '700', color: '#111', marginTop: 2 },
  planMeta:       { fontSize: 12, color: '#666', marginTop: 2 },
  savings:        { fontSize: 12, color: '#2ECC71', paddingHorizontal: 16, marginBottom: 10 },
  costBox:        { backgroundColor: '#fff', padding: 16, marginBottom: 12 },
  costLabel:      { fontSize: 12, color: '#999', marginBottom: 4 },
  costValue:      { fontSize: 16, fontWeight: '700', color: '#111' },
  missingText:    { marginTop: 6, fontSize: 12, color: '#E74C3C' },
  sectionTitle:   { fontSize: 14, fontWeight: '700', color: '#555', paddingHorizontal: 16, paddingVertical: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  ingredientRow:  { backgroundColor: '#fff', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  nameRow:        { flexDirection: 'row', alignItems: 'center', gap: 6 },
  ingredientName: { fontSize: 15, color: '#111' },
  promoTag:       { fontSize: 10, fontWeight: '700', color: '#fff', backgroundColor: '#C8102E', borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1, overflow: 'hidden' },
  ingredientStore:{ fontSize: 12, color: '#999', marginTop: 2 },
  upcoming:       { fontSize: 12, color: '#C8102E', marginTop: 2 },
  ingredientAmt:  { fontSize: 14, color: '#666', marginRight: 12 },
  costCol:        { minWidth: 62, alignItems: 'flex-end' },
  wasPrice:       { fontSize: 11, color: '#bbb', textDecorationLine: 'line-through' },
  ingredientCost: { fontSize: 14, fontWeight: '600', color: '#2ECC71', textAlign: 'right' },
  noCost:         { color: '#ccc' },
  btn:            { margin: 16, backgroundColor: '#2ECC71', borderRadius: 14, paddingVertical: 16, alignItems: 'center' },
  btnDisabled:    { opacity: 0.6 },
  btnText:        { color: '#fff', fontSize: 16, fontWeight: '700' },
});
