import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity,
  ScrollView, ActivityIndicator, Alert, Image,
} from 'react-native';
import { processReceiptFull, type ProcessedReceiptResult } from '../services/receiptService';
import { supabase } from '../lib/supabase';

export function ReceiptScreen() {
  const [result, setResult]   = useState<ProcessedReceiptResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [imageUri, setImageUri] = useState<string | null>(null);

  // Placeholder: w docelowej wersji użyj react-native-image-picker
  const pickAndProcess = async () => {
    Alert.alert(
      'Skanuj paragon',
      'Integracja z aparatem wymaga react-native-image-picker. Teraz test z przykładowym URL.',
      [
        { text: 'Anuluj', style: 'cancel' },
        {
          text: 'Test z URL',
          onPress: async () => {
            setLoading(true);
            try {
              const { data: { user } } = await supabase.auth.getUser();
              if (!user) { Alert.alert('Zaloguj się', 'Musisz być zalogowany.'); return; }
              const r = await processReceiptFull(user.id, 'https://example.com/test-receipt.jpg');
              setResult(r);
              setImageUri('https://example.com/test-receipt.jpg');
            } catch (e) {
              Alert.alert('Błąd', String(e));
            } finally {
              setLoading(false);
            }
          },
        },
      ]
    );
  };

  return (
    <ScrollView style={s.container} contentContainerStyle={{ paddingBottom: 40 }}>
      <Text style={s.header}>Paragon</Text>

      {/* Upload */}
      <TouchableOpacity style={s.uploadBtn} onPress={pickAndProcess} disabled={loading} activeOpacity={0.8}>
        {loading
          ? <ActivityIndicator color="#fff" />
          : <>
              <Text style={s.uploadIcon}>📷</Text>
              <Text style={s.uploadText}>Zrób zdjęcie paragonu</Text>
            </>
        }
      </TouchableOpacity>

      {/* Podgląd zdjęcia */}
      {imageUri && <Image source={{ uri: imageUri }} style={s.preview} resizeMode="cover" />}

      {/* Wyniki OCR */}
      {result && (
        <>
          <View style={s.statusRow}>
            <Text style={s.statusText}>
              {result.success ? '✅ Przetworzono pomyślnie' : '⚠️ Częściowe wyniki'}
            </Text>
          </View>

          <Text style={s.sectionTitle}>Rozpoznane pozycje ({result.items?.length ?? 0})</Text>
          {(result.items ?? []).map((item, i) => (
            <View key={i} style={s.itemCard}>
              <View style={s.itemTop}>
                <Text style={s.itemRaw}>{item.rawName}</Text>
                {item.confidence != null && (
                  <View style={[s.confBadge, { backgroundColor: item.confidence > 0.8 ? '#e8f8ef' : '#fff5e0' }]}>
                    <Text style={[s.confText, { color: item.confidence > 0.8 ? '#2ECC71' : '#F39C12' }]}>
                      {Math.round(item.confidence * 100)}%
                    </Text>
                  </View>
                )}
              </View>
              {item.matchedName && item.matchedName !== item.rawName && (
                <Text style={s.itemMatched}>→ {item.matchedName}</Text>
              )}
              <View style={s.itemBottom}>
                {item.grossPrice != null && <Text style={s.itemPrice}>{item.grossPrice.toFixed(2)} zł</Text>}
                {item.quantity   != null && <Text style={s.itemQty}>x{item.quantity}</Text>}
              </View>
            </View>
          ))}

          {result.error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{result.error}</Text>
            </View>
          )}
        </>
      )}

      {!result && !loading && (
        <Text style={s.hint}>Zeskanuj paragon, żeby automatycznie rozpoznać produkty i dopasować je do składników.</Text>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container:   { flex: 1, backgroundColor: '#f5f5f5' },
  header:      { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff', marginBottom: 12 },
  uploadBtn:   { margin: 16, backgroundColor: '#2ECC71', borderRadius: 16, paddingVertical: 28, alignItems: 'center', gap: 8 },
  uploadIcon:  { fontSize: 36 },
  uploadText:  { color: '#fff', fontSize: 16, fontWeight: '700' },
  preview:     { width: '100%', height: 180, marginBottom: 12 },
  statusRow:   { backgroundColor: '#fff', padding: 14, marginHorizontal: 12, borderRadius: 10, marginBottom: 4 },
  statusText:  { fontSize: 15, fontWeight: '600', color: '#111' },
  sectionTitle:{ fontSize: 12, fontWeight: '700', color: '#888', paddingHorizontal: 16, paddingTop: 12, paddingBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  itemCard:    { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 8, borderRadius: 10, padding: 14 },
  itemTop:     { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  itemRaw:     { flex: 1, fontSize: 15, fontWeight: '600', color: '#111' },
  confBadge:   { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  confText:    { fontSize: 12, fontWeight: '700' },
  itemMatched: { fontSize: 13, color: '#666', marginBottom: 6 },
  itemBottom:  { flexDirection: 'row', gap: 12 },
  itemPrice:   { fontSize: 15, fontWeight: '700', color: '#2ECC71' },
  itemQty:     { fontSize: 14, color: '#999' },
  errorBox:    { margin: 12, backgroundColor: '#fff5f5', borderRadius: 10, padding: 12 },
  errorText:   { color: '#E74C3C', fontSize: 13 },
  hint:        { textAlign: 'center', marginTop: 32, marginHorizontal: 32, color: '#aaa', lineHeight: 22 },
});
