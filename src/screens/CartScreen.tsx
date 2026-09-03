import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, Alert, ScrollView,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { buildCartForRecipes, type CartResult, type CartIngredientLine } from '../services/cartService';
import { getPublicRecipes } from '../services/recipeService';
import { Recipe } from '../model/Recipe';

export function CartScreen() {
  const [cart, setCart]         = useState<CartResult | null>(null);
  const [recipes, setRecipes]   = useState<Recipe[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading]   = useState(false);
  const [phase, setPhase]       = useState<'pick' | 'result'>('pick');

  useFocusEffect(useCallback(() => {
    getPublicRecipes().then(setRecipes).catch(console.error);
  }, []));

  const toggleRecipe = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const buildCart = async () => {
    if (selected.size === 0) { Alert.alert('Zaznacz przepis'); return; }
    setLoading(true);
    try {
      const portions = recipes
        .filter(r => selected.has(r.id))
        .map(r => ({ recipeId: r.id, portions: r.portions ?? 1 }));
      const result = await buildCartForRecipes(portions);
      setCart(result);
      setPhase('result');
    } catch (e) {
      Alert.alert('Błąd', String(e));
    } finally {
      setLoading(false);
    }
  };

  if (phase === 'pick') {
    return (
      <View style={s.container}>
        <Text style={s.header}>Wybierz przepisy</Text>
        <FlatList
          data={recipes}
          keyExtractor={r => r.id}
          renderItem={({ item }) => {
            const checked = selected.has(item.id);
            return (
              <TouchableOpacity style={[s.pickCard, checked && s.pickCardActive]} onPress={() => toggleRecipe(item.id)} activeOpacity={0.75}>
                <Text style={s.pickCheck}>{checked ? '☑' : '☐'}</Text>
                <Text style={[s.pickTitle, checked && s.pickTitleActive]}>{item.title}</Text>
                <Text style={s.pickMeta}>{item.portions ?? 1} porcji</Text>
              </TouchableOpacity>
            );
          }}
          contentContainerStyle={{ padding: 12, paddingBottom: 100 }}
          ListEmptyComponent={<Text style={s.empty}>Brak przepisów w bazie.</Text>}
        />
        <View style={s.bottomBar}>
          <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={buildCart} disabled={loading} activeOpacity={0.8}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>🛒 Buduj koszyk ({selected.size})</Text>}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // --- Widok wyników ---
  const cheapestId = cart?.cheapestStoreId;

  return (
    <ScrollView style={s.container} contentContainerStyle={{ paddingBottom: 40 }}>
      <Text style={s.header}>Koszyk</Text>

      {/* Dwie ceny: jeden sklep vs. najtaniej łącząc sklepy */}
      {cart && (cart.totalCostPln != null || cart.mixedStoreTotalPln != null) && (
        <View style={s.totalsBox}>
          {cart.totalCostPln != null && (
            <View style={s.totalCard}>
              <Text style={s.totalLabel}>Wszystko w {cart.cheapestStoreName ?? 'jednym sklepie'}</Text>
              <Text style={s.totalValue}>{cart.totalCostPln.toFixed(2)} zł</Text>
            </View>
          )}
          {cart.mixedStoreTotalPln != null && (
            <View style={[s.totalCard, s.totalCardAlt]}>
              <Text style={s.totalLabel}>Najtaniej łącząc sklepy</Text>
              <Text style={s.totalValue}>{cart.mixedStoreTotalPln.toFixed(2)} zł</Text>
            </View>
          )}
        </View>
      )}

      {/* Podsumowanie sklepów */}
      {cart && cart.storeSummaries.length > 0 && (
        <View style={s.storesBox}>
          <Text style={s.sectionTitle}>Porównanie sklepów</Text>
          {cart.storeSummaries
            .sort((a, b) => a.totalCostPln - b.totalCostPln)
            .map(store => (
              <View key={store.storeId} style={[s.storeRow, store.storeId === cheapestId && s.storeRowBest]}>
                <View style={{ flex: 1 }}>
                  <Text style={s.storeName}>{store.storeName} {store.storeId === cheapestId ? '⭐' : ''}</Text>
                  <Text style={s.storeCoverage}>Pokrycie: {store.coveragePercent}%</Text>
                </View>
                <Text style={[s.storeTotal, store.storeId === cheapestId && s.storeTotalBest]}>
                  {store.totalCostPln.toFixed(2)} zł
                </Text>
              </View>
            ))}
        </View>
      )}

      {/* Brakujące ceny */}
      {cart && cart.missingPrices.length > 0 && (
        <View style={s.missingBox}>
          <Text style={s.missingTitle}>Brak cen dla:</Text>
          <Text style={s.missingList}>{cart.missingPrices.join(', ')}</Text>
        </View>
      )}

      {/* Lista składników */}
      <Text style={s.sectionTitle}>Lista zakupów</Text>
      {cart?.lines.map((line: CartIngredientLine) => (
        <View key={line.ingredientId} style={s.lineCard}>
          <View style={s.lineTop}>
            <Text style={s.lineName}>{line.ingredientName}</Text>
            <Text style={s.lineAmt}>{line.totalAmount} {line.unit}</Text>
          </View>
          {line.bestProduct ? (
            <View style={s.lineProduct}>
              <Text style={s.lineProductName}>{line.bestProduct.productName}</Text>
              <Text style={s.lineProductStore}>{line.bestProduct.storeName}</Text>
              <Text style={s.lineProductCost}>{line.bestProduct.totalCostPln.toFixed(2)} zł</Text>
            </View>
          ) : (
            <Text style={s.noCost}>Brak dopasowania</Text>
          )}
        </View>
      ))}

      <TouchableOpacity style={[s.btn, { margin: 16 }]} onPress={() => { setPhase('pick'); setCart(null); }} activeOpacity={0.8}>
        <Text style={s.btnText}>← Zmień przepisy</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#f5f5f5' },
  header:          { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff' },
  empty:           { textAlign: 'center', marginTop: 60, color: '#999' },
  sectionTitle:    { fontSize: 12, fontWeight: '700', color: '#888', paddingHorizontal: 16, paddingTop: 16, paddingBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  // Dwie ceny
  totalsBox:       { flexDirection: 'row', gap: 10, padding: 12 },
  totalCard:       { flex: 1, backgroundColor: '#fff', borderRadius: 12, padding: 14, borderWidth: 1.5, borderColor: '#2ECC71' },
  totalCardAlt:    { borderColor: '#F39C12' },
  totalLabel:      { fontSize: 12, color: '#888', marginBottom: 6 },
  totalValue:      { fontSize: 20, fontWeight: '700', color: '#111' },
  // Wybór przepisów
  pickCard:        { backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1.5, borderColor: 'transparent' },
  pickCardActive:  { borderColor: '#2ECC71', backgroundColor: '#f0faf5' },
  pickCheck:       { fontSize: 20 },
  pickTitle:       { flex: 1, fontSize: 15, color: '#111' },
  pickTitleActive: { color: '#2ECC71', fontWeight: '600' },
  pickMeta:        { fontSize: 13, color: '#999' },
  bottomBar:       { position: 'absolute', bottom: 0, left: 0, right: 0, padding: 16, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#eee' },
  btn:             { backgroundColor: '#2ECC71', borderRadius: 12, paddingVertical: 15, alignItems: 'center' },
  btnDisabled:     { opacity: 0.6 },
  btnText:         { color: '#fff', fontSize: 16, fontWeight: '700' },
  // Sklepy
  storesBox:       { backgroundColor: '#fff', marginBottom: 4 },
  storeRow:        { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f5f5f5' },
  storeRowBest:    { backgroundColor: '#f0faf5' },
  storeName:       { fontSize: 15, fontWeight: '600', color: '#111' },
  storeCoverage:   { fontSize: 12, color: '#999', marginTop: 2 },
  storeTotal:      { fontSize: 16, fontWeight: '700', color: '#555' },
  storeTotalBest:  { color: '#2ECC71' },
  // Brakujące
  missingBox:      { backgroundColor: '#fff5f5', margin: 12, borderRadius: 10, padding: 12 },
  missingTitle:    { fontSize: 13, fontWeight: '700', color: '#E74C3C', marginBottom: 4 },
  missingList:     { fontSize: 13, color: '#c0392b' },
  // Linie składników
  lineCard:        { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 8, borderRadius: 10, padding: 14 },
  lineTop:         { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  lineName:        { fontSize: 15, fontWeight: '600', color: '#111' },
  lineAmt:         { fontSize: 14, color: '#666' },
  lineProduct:     { flexDirection: 'row', alignItems: 'center', gap: 6 },
  lineProductName: { flex: 1, fontSize: 13, color: '#555' },
  lineProductStore:{ fontSize: 12, color: '#999' },
  lineProductCost: { fontSize: 14, fontWeight: '700', color: '#2ECC71' },
  noCost:          { fontSize: 13, color: '#ccc', fontStyle: 'italic' },
});
