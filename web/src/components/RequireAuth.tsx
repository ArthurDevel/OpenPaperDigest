'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader } from 'lucide-react';
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

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        <Loader className="mr-2 h-4 w-4 animate-spin" />
        Loading session...
      </div>
    );
  }

  if (!user?.id) {
    return null;
  }

  return <>{children}</>;
}
