import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { StorePriceComparison } from '../services/recipeService';

type Props = { comparisons: StorePriceComparison[] };

const money = (v: number | null) => (v != null ? `${v.toFixed(2)} zł` : '—');

/**
 * Sklep obok sklepu, każdy z dwiema kolumnami cen: "Pojedynczo" (najmniejsze
 * dostępne opakowanie — tyle, ile faktycznie trzeba) i "Wielosztuka"
 * (najniższa suma, nawet jeśli wymaga kupna większego opakowania/promocji
 * warunkowej). Ceny "z kartą" nie mają tu osobnej kolumny — jeśli to one
 * wygrywają jako najtańsza oferta, po prostu są tą liczbą, którą widać.
 */
export function StorePriceComparisonTable({ comparisons }: Props) {
  if (comparisons.length === 0) return null;

  // Wszystkie plany liczone są z tych samych `rows` (patrz
  // calculateStorePriceComparison), więc kolejność składników jest
  // identyczna w każdym z nich — bezpiecznie zrównoleglamy po indeksie.
  const ingredientNames = comparisons[0]?.smallestPackage.lines.map(l => l.ingredientName) ?? [];

  return (
    <View style={s.wrap}>
      <Text style={s.title}>Porównanie sklepów</Text>

      <View style={s.headerRow}>
        <View style={s.nameCol} />
        {comparisons.map(c => (
          <View key={c.storeName} style={s.storeHeader}>
            <Text style={s.storeName}>{c.storeName}</Text>
            <View style={s.subHeaderRow}>
              <Text style={s.subHeader}>Pojedynczo</Text>
              <Text style={s.subHeader}>Wielosztuka</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={[s.row, s.totalRow]}>
        <Text style={[s.ingredientName, s.totalLabel]}>Razem</Text>
        {comparisons.map(c => (
          <View key={c.storeName} style={s.storeCell}>
            <Text style={s.totalPrice}>{money(c.smallestPackage.totalCostPln)}</Text>
            <Text style={s.totalPrice}>{money(c.bestValue.totalCostPln)}</Text>
          </View>
        ))}
      </View>

      {ingredientNames.map((name, i) => (
        <View key={name} style={s.row}>
          <Text style={s.ingredientName} numberOfLines={1}>{name}</Text>
          {comparisons.map(c => (
            <View key={c.storeName} style={s.storeCell}>
              <Text style={s.cellPrice}>{money(c.smallestPackage.lines[i]?.costPln ?? null)}</Text>
              <Text style={s.cellPrice}>{money(c.bestValue.lines[i]?.costPln ?? null)}</Text>
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  wrap:          { backgroundColor: '#fff', marginBottom: 12, paddingVertical: 12 },
  title:         { fontSize: 14, fontWeight: '700', color: '#555', paddingHorizontal: 16, paddingBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  headerRow:     { flexDirection: 'row', paddingHorizontal: 16, paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: '#eee' },
  nameCol:       { flex: 1.4 },
  storeHeader:   { flex: 1, alignItems: 'center' },
  storeName:     { fontSize: 12, fontWeight: '700', color: '#111' },
  subHeaderRow:  { flexDirection: 'row', gap: 4, marginTop: 2, width: '100%' },
  subHeader:     { flex: 1, fontSize: 9, color: '#999', textAlign: 'center' },
  row:           { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f5f5f5' },
  totalRow:      { backgroundColor: '#f9fdfb' },
  ingredientName:{ flex: 1.4, fontSize: 13, color: '#333' },
  totalLabel:    { fontWeight: '700', color: '#111' },
  storeCell:     { flex: 1, flexDirection: 'row', gap: 4 },
  cellPrice:     { flex: 1, fontSize: 12, color: '#666', textAlign: 'center' },
  totalPrice:    { flex: 1, fontSize: 13, fontWeight: '700', color: '#2ECC71', textAlign: 'center' },
});
