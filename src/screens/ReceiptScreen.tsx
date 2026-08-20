import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity,
  ScrollView, ActivityIndicator, Alert, Image,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { launchCamera, launchImageLibrary, type Asset } from 'react-native-image-picker';
import {
  processReceiptFull, getMyReceipts,
  type OcrResult, type Receipt,
} from '../services/receiptService';
import { supabase } from '../lib/supabase';

type Mode = 'idle' | 'processing' | 'result';

export function ReceiptScreen() {
  const [mode, setMode]       = useState<Mode>('idle');
  const [result, setResult]   = useState<OcrResult | null>(null);
  const [history, setHistory] = useState<Receipt[]>([]);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [userId, setUserId]   = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setUserId(user.id);
        getMyReceipts(user.id).then(setHistory).catch(console.error);
      }
    });
  }, []));

  const handleAsset = async (asset: Asset) => {
    if (!asset.uri) return;
    if (!userId) { Alert.alert('Zaloguj się', 'Musisz być zalogowany.'); return; }

    setImageUri(asset.uri);
    setMode('processing');
    setResult(null);

    try {
      const ocr = await processReceiptFull({
        userId,
        fileUri:  asset.uri,
        mimeType: asset.type ?? 'image/jpeg',
      });
      setResult(ocr);
      setMode('result');
      // Odśwież historię
      getMyReceipts(userId).then(setHistory).catch(console.error);
    } catch (e: any) {
      Alert.alert('Błąd OCR', e?.message ?? String(e));
      setMode('idle');
    }
  };

  const openCamera = () =>
    launchCamera(
      { mediaType: 'photo', quality: 0.8, saveToPhotos: false },
      ({ assets, didCancel, errorMessage }) => {
        if (didCancel || !assets?.[0]) return;
        if (errorMessage) { Alert.alert('Błąd aparatu', errorMessage); return; }
        handleAsset(assets[0]);
      }
    );

  const openGallery = () =>
    launchImageLibrary(
      { mediaType: 'photo', quality: 0.8 },
      ({ assets, didCancel, errorMessage }) => {
        if (didCancel || !assets?.[0]) return;
        if (errorMessage) { Alert.alert('Błąd galerii', errorMessage); return; }
        handleAsset(assets[0]);
      }
    );

  const reset = () => { setMode('idle'); setResult(null); setImageUri(null); };

  return (
    <ScrollView style={s.container} contentContainerStyle={{ paddingBottom: 48 }}>
      <Text style={s.header}>Paragon</Text>

      {/* Przyciski akcji */}
      {mode === 'idle' && (
        <View style={s.actionRow}>
          <TouchableOpacity style={s.actionBtn} onPress={openCamera} activeOpacity={0.8}>
            <Text style={s.actionIcon}>📷</Text>
            <Text style={s.actionLabel}>Aparat</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.actionBtn, s.actionBtnSecondary]} onPress={openGallery} activeOpacity={0.8}>
            <Text style={s.actionIcon}>🖼️</Text>
            <Text style={[s.actionLabel, { color: '#2ECC71' }]}>Galeria</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Podgląd zdjęcia */}
      {imageUri && (
        <Image source={{ uri: imageUri }} style={s.preview} resizeMode="cover" />
      )}

      {/* Spinner */}
      {mode === 'processing' && (
        <View style={s.processingBox}>
          <ActivityIndicator size="large" color="#2ECC71" />
          <Text style={s.processingText}>Przetwarzam paragon…</Text>
          <Text style={s.processingHint}>OCR może potrwać do 60 sekund</Text>
        </View>
      )}

      {/* Wyniki OCR */}
      {mode === 'result' && result && (
        <>
          <View style={s.summaryBox}>
            <Text style={s.summaryTitle}>✅ Przetworzono pomyślnie</Text>
            <Text style={s.summaryMeta}>
              {result.items.length} pozycji · {result.itemsMatched} dopasowań · {result.pricesSaved} cen zapisanych
            </Text>
          </View>

          <Text style={s.sectionTitle}>Rozpoznane pozycje</Text>
          {result.items.map((item, i) => (
            <View key={item.id ?? i} style={s.itemCard}>
              <View style={s.itemTop}>
                <Text style={s.itemRaw}>{item.raw_name}</Text>
                {item.confidence != null && (
                  <View style={[
                    s.confBadge,
                    { backgroundColor: item.confidence > 0.8 ? '#e8f8ef' : '#fff5e0' },
                  ]}>
                    <Text style={[
                      s.confText,
                      { color: item.confidence > 0.8 ? '#2ECC71' : '#F39C12' },
                    ]}>
                      {Math.round(item.confidence * 100)}%
                    </Text>
                  </View>
                )}
              </View>
              {item.matched_name && item.matched_name !== item.raw_name && (
                <Text style={s.itemMatched}>→ {item.matched_name}</Text>
              )}
              <View style={s.itemBottom}>
                {item.gross_price != null && (
                  <Text style={s.itemPrice}>{item.gross_price.toFixed(2)} zł</Text>
                )}
                {item.quantity != null && item.quantity !== 1 && (
                  <Text style={s.itemQty}>x{item.quantity}</Text>
                )}
                {item.unit && <Text style={s.itemUnit}>{item.unit}</Text>}
              </View>
            </View>
          ))}

          <TouchableOpacity style={[s.actionBtn, { margin: 16 }]} onPress={reset} activeOpacity={0.8}>
            <Text style={s.actionIcon}>📷</Text>
            <Text style={s.actionLabel}>Skanuj następny</Text>
          </TouchableOpacity>
        </>
      )}

      {/* Historia */}
      {mode === 'idle' && history.length > 0 && (
        <>
          <Text style={s.sectionTitle}>Historia ({history.length})</Text>
          {history.slice(0, 10).map(r => (
            <View key={r.id} style={s.historyRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.historyDate}>{r.receipt_date ?? '—'}</Text>
                <Text style={s.historyStatus}>{r.ocr_status}</Text>
              </View>
              <View style={[
                s.statusDot,
                { backgroundColor: r.ocr_status === 'done' ? '#2ECC71' : r.ocr_status === 'error' ? '#E74C3C' : '#F39C12' },
              ]} />
            </View>
          ))}
        </>
      )}

      {mode === 'idle' && !userId && (
        <Text style={s.hint}>Zaloguj się, żeby skanować paragony i zapisywać historię.</Text>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#f5f5f5' },
  header:         { fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 56, backgroundColor: '#fff', marginBottom: 8 },
  actionRow:      { flexDirection: 'row', padding: 12, gap: 12 },
  actionBtn:      { flex: 1, backgroundColor: '#2ECC71', borderRadius: 14, paddingVertical: 20, alignItems: 'center', gap: 6 },
  actionBtnSecondary: { backgroundColor: '#fff', borderWidth: 1.5, borderColor: '#2ECC71' },
  actionIcon:     { fontSize: 28 },
  actionLabel:    { color: '#fff', fontWeight: '700', fontSize: 14 },
  preview:        { width: '100%', height: 200, marginBottom: 8 },
  processingBox:  { alignItems: 'center', padding: 40, gap: 12 },
  processingText: { fontSize: 16, fontWeight: '600', color: '#333' },
  processingHint: { fontSize: 13, color: '#999' },
  summaryBox:     { backgroundColor: '#fff', margin: 12, borderRadius: 12, padding: 16 },
  summaryTitle:   { fontSize: 16, fontWeight: '700', color: '#111', marginBottom: 4 },
  summaryMeta:    { fontSize: 13, color: '#666' },
  sectionTitle:   { fontSize: 12, fontWeight: '700', color: '#888', paddingHorizontal: 16, paddingVertical: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  itemCard:       { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 8, borderRadius: 10, padding: 14 },
  itemTop:        { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  itemRaw:        { flex: 1, fontSize: 15, fontWeight: '600', color: '#111' },
  confBadge:      { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  confText:       { fontSize: 12, fontWeight: '700' },
  itemMatched:    { fontSize: 13, color: '#666', marginBottom: 6 },
  itemBottom:     { flexDirection: 'row', gap: 10, alignItems: 'center' },
  itemPrice:      { fontSize: 15, fontWeight: '700', color: '#2ECC71' },
  itemQty:        { fontSize: 14, color: '#999' },
  itemUnit:       { fontSize: 13, color: '#bbb' },
  historyRow:     { backgroundColor: '#fff', flexDirection: 'row', alignItems: 'center', marginHorizontal: 12, marginBottom: 6, borderRadius: 10, padding: 14 },
  historyDate:    { fontSize: 14, fontWeight: '600', color: '#111' },
  historyStatus:  { fontSize: 12, color: '#999', marginTop: 2 },
  statusDot:      { width: 10, height: 10, borderRadius: 5 },
  hint:           { textAlign: 'center', marginTop: 32, marginHorizontal: 32, color: '#aaa', lineHeight: 22 },
});
