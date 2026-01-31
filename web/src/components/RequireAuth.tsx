'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authClient } from '../services/auth';

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { data: session, isPending } = authClient.useSession();
  const router = useRouter();

  useEffect(() => {
    if (isPending) return;
    if (!session?.user?.id) {
      router.replace('/login');
    }
  }, [session?.user?.id, isPending, router]);

  return <>{children}</>;
}


