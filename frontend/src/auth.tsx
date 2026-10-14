import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from './api';
import { clearAuthToken, getAuthClient } from './auth-client';
import { queryClient } from './query';
import type { Member } from './types';

interface AuthState {
  member: Member | null;
  email: string | null;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [member, setMember] = useState<Member | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const identity = useRef<string | null>(null);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const requestGeneration = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const client = await getAuthClient();
      const session = await client.getSession();
      if (session.error) throw new Error('Could not restore your session. Try again.');
      if (requestGeneration !== generation.current) return;
      const sessionEmail = session.data?.user?.email ?? null;
      setEmail(sessionEmail);
      if (!sessionEmail) {
        clearAuthToken();
        queryClient.clear();
        identity.current = null;
        setMember(null);
        return;
      }
      clearAuthToken();
      const current = await api.me();
      if (requestGeneration !== generation.current) return;
      if (identity.current !== current.id) queryClient.clear();
      identity.current = current.id;
      setMember(current);
    } catch (failure) {
      if (requestGeneration !== generation.current) return;
      setMember(null);
      queryClient.clear();
      setError(failure instanceof ApiError || failure instanceof Error ? failure.message : 'Unable to check your access.');
    } finally {
      if (requestGeneration === generation.current) setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    const client = await getAuthClient();
    const result = await client.signOut();
    if (result.error) throw new Error('Sign out failed. Please try again.');
    generation.current += 1;
    clearAuthToken();
    queryClient.clear();
    identity.current = null;
    setMember(null);
    setEmail(null);
    setError('');
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); return () => { generation.current += 1; }; }, [refresh]);
  useEffect(() => {
    const expired = () => {
      generation.current += 1;
      clearAuthToken();
      queryClient.clear();
      setMember(null);
      setEmail(null);
      setLoading(false);
      setError('Your session expired. Sign in again.');
    };
    window.addEventListener('copilot-session-expired', expired);
    return () => window.removeEventListener('copilot-session-expired', expired);
  }, []);

  return <AuthContext.Provider value={{ member, email, loading, error, refresh, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('AuthProvider is missing.');
  return context;
}
