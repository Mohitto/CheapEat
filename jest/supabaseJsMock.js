// Testy jednostkowe nie powinny nigdy uderzać w prawdziwy Supabase — bez tego
// mocka ekrany (Feed/Cart/Preferences/...) odpalają realne zapytania sieciowe
// przy montowaniu, co wiesza Jest (proces czeka na zamknięcie połączeń).
function makeChainable() {
  return new Proxy(() => {}, {
    get(_target, prop) {
      if (prop === 'then') {
        return (resolve) => resolve({ data: [], error: null });
      }
      return () => makeChainable();
    },
  });
}

function createClient() {
  return {
    from: () => makeChainable(),
    rpc: () => Promise.resolve({ data: null, error: null }),
    storage: {
      from: () => ({ upload: () => Promise.resolve({ data: null, error: null }) }),
    },
    functions: {
      invoke: () => Promise.resolve({ data: null, error: null }),
    },
    auth: {
      getUser: () => Promise.resolve({ data: { user: null } }),
      getSession: () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInAnonymously: () => Promise.resolve({ data: { session: null }, error: null }),
      signInWithOAuth: () => Promise.resolve({ data: {}, error: null }),
      signUp: () => Promise.resolve({ data: { session: null }, error: null }),
      signInWithPassword: () => Promise.resolve({ data: { session: null }, error: null }),
      updateUser: () => Promise.resolve({ data: {}, error: null }),
      signOut: () => Promise.resolve({ error: null }),
    },
  };
}

module.exports = { createClient };
