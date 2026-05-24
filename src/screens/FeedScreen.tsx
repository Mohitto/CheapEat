import React from 'react';
import { View, Text, StyleSheet, FlatList } from 'react-native';

const MOCK_RECIPES = [
  { id: '1', title: 'Kurczak z ryżem', protein: 45, kcal: 520, prepMin: 25, price: 12.5 },
  { id: '2', title: 'Makaron z tuńczykiem', protein: 38, kcal: 480, prepMin: 15, price: 9.8 },
  { id: '3', title: 'Jajecznica z warzywami', protein: 28, kcal: 350, prepMin: 10, price: 6.2 },
];

export function FeedScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.header}>Przepisy</Text>
      <FlatList
        data={MOCK_RECIPES}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.title}>{item.title}</Text>
            <View style={styles.row}>
              <Text style={styles.meta}>🥩 {item.protein}g białka</Text>
              <Text style={styles.meta}>⏱ {item.prepMin} min</Text>
              <Text style={styles.price}>{item.price.toFixed(2)} zł</Text>
            </View>
          </View>
        )}
        contentContainerStyle={styles.list}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff' },
  list: { padding: 12 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  title: { fontSize: 16, fontWeight: '600', marginBottom: 8, color: '#111' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meta: { fontSize: 13, color: '#666' },
  price: { marginLeft: 'auto', fontSize: 15, fontWeight: '700', color: '#2ECC71' },
});
