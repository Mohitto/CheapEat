import 'react-native-url-polyfill/auto';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';

// TODO: gdy schema się ustabilizuje, wygeneruj prawdziwe typy przez
// `supabase gen types typescript` i podepnij je jako generic <Database> do createClient.
const SUPABASE_URL = 'https://ncksaaafqovbrvjetlcc.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5ja3NhYWFmcW92YnJ2amV0bGNjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYzMjc5MjcsImV4cCI6MjA5MTkwMzkyN30.qx_4eZuIf8xe9d5qeC5qhQjnvF8NdT9pBOuRYLgujls';

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
