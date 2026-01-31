'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from '@/services/auth';

/**
 * RequireAuth component that redirects unauthenticated users to login.
 * @param children - Child components to render when authenticated
 * @returns Children if authenticated, or redirects to /login
 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user?.id) {
      router.replace('/login');
    }
  }, [user?.id, isLoading, router]);

  return <>{children}</>;
}
