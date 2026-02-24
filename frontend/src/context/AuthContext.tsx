'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { setCurrentUser } from '@/lib/session-utils';
import type { User } from '@/types/chat';

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  reloadUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadUser() {
    try {
      const res = await apiFetch('/user/profile');

      if (!res.ok) {
        setUser(null);
        setCurrentUser(null);
        return;
      }

      const contentType = res.headers.get('content-type') ?? '';
      if (!contentType.includes('application/json')) {
        setUser(null);
        setCurrentUser(null);
        return;
      }

      let data: Record<string, unknown>;
      try {
        data = await res.json();
      } catch {
        setUser(null);
        setCurrentUser(null);
        return;
      }

      const u: User = {
        id: (data.user_id as string) || (data.id as string) || (data.email as string),
        name: (data.user_name as string) || (data.name as string) || 'User',
        email: (data.user_email as string) || (data.email as string),
        is_admin: !!data.is_admin,
        excludable_developer_emails: Array.isArray(data.excludable_developer_emails)
          ? (data.excludable_developer_emails as string[])
          : undefined,
      };
      setUser(u);
      setCurrentUser(u);
    } catch {
      setUser(null);
      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, reloadUser: loadUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
