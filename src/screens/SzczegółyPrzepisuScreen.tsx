import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<RootStackParamList, 'SzczegółyPrzepisu'>;

export function SzczegółyPrzepisuScreen({ route }: Props) {
  const { recipeId } = route.params;

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>Szczegóły przepisu</Text>
      <Text style={styles.placeholder}>ID: {recipeId}{"\n\n"}Tu będą: opis krok po kroku, lista składników, warianty koszyka i porady przechowywania.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5', padding: 16 },
  header: { fontSize: 24, fontWeight: '700', marginBottom: 16, color: '#111' },
  placeholder: { fontSize: 14, color: '#888', lineHeight: 22 },
});
