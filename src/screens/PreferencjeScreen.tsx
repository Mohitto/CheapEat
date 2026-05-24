import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export function PreferencjeScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.header}>Preferencje składników</Text>
      <Text style={styles.placeholder}>Tu będzie lista składników z wyborem: Lubię / Średnie / Dodatek / Zakazane</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5', padding: 16, paddingTop: 56 },
  header: { fontSize: 24, fontWeight: '700', marginBottom: 16, color: '#111' },
  placeholder: { fontSize: 14, color: '#888', lineHeight: 22 },
});
