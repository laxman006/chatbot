'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { getApiBase } from '@/lib/api';
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
      const base = getApiBase();
      const res = await fetch(`${base}/user/profile`, {
        credentials: 'include',
      });

      if (!res.ok) {
        setUser(null);
        setCurrentUser(null);
      } else {
        const data = await res.json();
        const u: User = {
          id: data.user_id || data.id || data.email,
          name: data.user_name || data.name || 'User',
          email: data.user_email || data.email,
          is_admin: !!data.is_admin,
          excludable_developer_emails: Array.isArray(data.excludable_developer_emails)
            ? data.excludable_developer_emails
            : undefined,
        };
        setUser(u);
        setCurrentUser(u);
      }
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
