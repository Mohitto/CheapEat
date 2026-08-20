/**
 * receiptService.ts — Receipt OCR
 *
 * Przepływ:
 * 1. Użytkownik fotografuje paragon (React Native Camera)
 * 2. uploadReceiptImage() — wgrywa zdjęcie do Supabase Storage (bucket: receipts)
 * 3. createReceiptRecord() — tworzy rekord w tabeli receipts (ocr_status='pending')
 * 4. triggerOcr() — woła Edge Function process-receipt
 * 5. pollReceiptStatus() — polling co 2s aż ocr_status='done'|'error'
 * 6. getReceiptItems() — pobiera pozycje z receipt_items
 */
import { supabase } from '../lib/supabase';

// ---------------------------------------------------------------------------
// Typy
// ---------------------------------------------------------------------------

export type ReceiptStatus = 'pending' | 'processing' | 'done' | 'error';

export type Receipt = {
  id: string;
  store_id: string | null;
  user_id: string;
  receipt_date: string | null;
  image_url: string | null;
  ocr_status: ReceiptStatus;
  created_at: string;
};

export type ReceiptItem = {
  id: string;
  receipt_id: string;
  store_product_id: string | null;
  raw_name: string;
  matched_name: string | null;
  gross_price: number | null;
  quantity: number;
  unit: string;
  confidence: number | null;
};

export type OcrResult = {
  receipt: Receipt;
  items: ReceiptItem[];
  itemsMatched: number;
  pricesSaved: number;
};

// ---------------------------------------------------------------------------
// Upload zdjęcia do Storage
// ---------------------------------------------------------------------------

/**
 * Wgrywa zdjęcie paragonu do Supabase Storage.
 * Zwraca ściekę pliku w buckecie (np. "userId/timestamp.jpg").
 */
export async function uploadReceiptImage(
  userId: string,
  fileUri: string,         // lokalny URI z React Native Camera
  mimeType = 'image/jpeg'
): Promise<string> {
  const fileName = `${userId}/${Date.now()}.jpg`;

  // Konwersja file URI -> Blob (React Native)
  const response = await fetch(fileUri);
  const blob = await response.blob();

  const { error } = await supabase.storage
    .from('receipts')
    .upload(fileName, blob, {
      contentType: mimeType,
      upsert: false,
    });

  if (error) throw new Error(`Upload failed: ${error.message}`);
  return fileName;
}

// ---------------------------------------------------------------------------
// Tworzenie rekordu paragonu
// ---------------------------------------------------------------------------

/**
 * Tworzy rekord paragonu w bazie z ocr_status='pending'.
 */
export async function createReceiptRecord(params: {
  userId: string;
  imageUrl: string;
  storeId?: string;
  receiptDate?: string;  // YYYY-MM-DD
}): Promise<Receipt> {
  const { data, error } = await supabase
    .from('receipts')
    .insert({
      user_id:      params.userId,
      image_url:    params.imageUrl,
      store_id:     params.storeId ?? null,
      receipt_date: params.receiptDate ?? new Date().toISOString().split('T')[0],
      ocr_status:   'pending',
    })
    .select()
    .single();

  if (error) throw new Error(`createReceiptRecord: ${error.message}`);
  return data as Receipt;
}

// ---------------------------------------------------------------------------
// Wywołanie Edge Function OCR
// ---------------------------------------------------------------------------

/**
 * Wywołuje Edge Function process-receipt.
 * Edge Function sama pobiera obraz ze Storage po image_url.
 */
export async function triggerOcr(receiptId: string): Promise<void> {
  const { error } = await supabase.functions.invoke('process-receipt', {
    body: { receipt_id: receiptId },
  });

  if (error) throw new Error(`triggerOcr: ${error.message}`);
}

// ---------------------------------------------------------------------------
// Polling statusu
// ---------------------------------------------------------------------------

/**
 * Czeka na zakończenie OCR (polling co intervalMs).
 * Timeout po maxWaitMs (domyślnie 60s).
 */
export async function pollReceiptStatus(
  receiptId: string,
  intervalMs = 2000,
  maxWaitMs  = 60000
): Promise<ReceiptStatus> {
  const deadline = Date.now() + maxWaitMs;

  while (Date.now() < deadline) {
    const { data, error } = await supabase
      .from('receipts')
      .select('ocr_status')
      .eq('id', receiptId)
      .single();

    if (error) throw new Error(`pollReceiptStatus: ${error.message}`);

    const status = data.ocr_status as ReceiptStatus;
    if (status === 'done' || status === 'error') return status;

    await new Promise<void>(resolve => setTimeout(resolve, intervalMs));
  }

  throw new Error('OCR timeout — paragon nie został przetworzony w czasie 60s');
}

// ---------------------------------------------------------------------------
// Pobieranie wyników
// ---------------------------------------------------------------------------

/**
 * Zwraca pozycje z przetworzonego paragonu.
 */
export async function getReceiptItems(receiptId: string): Promise<ReceiptItem[]> {
  const { data, error } = await supabase
    .from('receipt_items')
    .select('*')
    .eq('receipt_id', receiptId)
    .order('id');

  if (error) throw new Error(`getReceiptItems: ${error.message}`);
  return (data ?? []) as ReceiptItem[];
}

/**
 * Zwraca historię paragonów użytkownika.
 */
export async function getMyReceipts(userId: string): Promise<Receipt[]> {
  const { data, error } = await supabase
    .from('receipts')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });

  if (error) throw new Error(`getMyReceipts: ${error.message}`);
  return (data ?? []) as Receipt[];
}

// ---------------------------------------------------------------------------
// Kompletny flow (upload -> OCR -> wyniki)
// ---------------------------------------------------------------------------

/**
 * Jeden-wywołanie pełny flow:
 * upload zdjęcia -> utwórz rekord -> odpal OCR -> czekaj -> zwroć wyniki
 */
export async function processReceiptFull(params: {
  userId: string;
  fileUri: string;
  storeId?: string;
  receiptDate?: string;
  mimeType?: string;
}): Promise<OcrResult> {
  // 1. Upload
  const imageUrl = await uploadReceiptImage(
    params.userId,
    params.fileUri,
    params.mimeType
  );

  // 2. Utwórz rekord
  const receipt = await createReceiptRecord({
    userId:      params.userId,
    imageUrl,
    storeId:     params.storeId,
    receiptDate: params.receiptDate,
  });

  // 3. Wywołaj OCR asynchronicznie
  await triggerOcr(receipt.id);

  // 4. Czekaj na wynik
  const finalStatus = await pollReceiptStatus(receipt.id);

  if (finalStatus === 'error') {
    throw new Error('OCR zakończony błędem — sprawdź zdjęcie paragonu');
  }

  // 5. Pobierz wyniki
  const items = await getReceiptItems(receipt.id);
  const itemsMatched = items.filter(i => i.store_product_id !== null).length;
  const pricesSaved  = items.filter(i => i.gross_price !== null && i.store_product_id !== null).length;

  // Odśwież dane receipt
  const { data: updatedReceipt } = await supabase
    .from('receipts')
    .select('*')
    .eq('id', receipt.id)
    .single();

  return {
    receipt: (updatedReceipt ?? receipt) as Receipt,
    items,
    itemsMatched,
    pricesSaved,
  };
}
