'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) {
      router.replace('/chat/new');
    }
  }, [user, loading, router]);

  if (loading) return null;
  if (!user?.is_admin) return null;

  return <>{children}</>;
}
