'use client';

import React from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { authClient } from '../../services/auth';
import UserSidebar from '../../components/UserSidebar';
import RequireAuth from '../../components/RequireAuth';

type TabItem = {
  href: string;
  label: string;
};

const TAB_ITEMS: TabItem[] = [
  { href: '/user/list', label: 'My list' },
  { href: '/user/requests', label: 'My requests' },
];

/**
 * User layout with responsive sidebar and mobile tabs
 * @param children - Child components to render in main content area
 * @returns Layout with sidebar (desktop) or horizontal tabs (mobile)
 */
export default function UserLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  /**
   * Handles user logout
   */
  const handleLogout = async (): Promise<void> => {
    try {
      await authClient.signOut();
    } catch {}
    router.replace('/');
  };

  return (
    <RequireAuth>
      <div className="flex flex-1 min-h-0 h-full overflow-hidden">
        {/* Mobile Tabs */}
        <div className="lg:hidden w-full flex flex-col min-h-0 h-full">
          <div className="flex-shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-end justify-between px-4">
              <div className="flex -mb-px overflow-x-auto">
                {TAB_ITEMS.map((item) => {
                  const isActive = pathname?.startsWith(item.href);
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      className={`whitespace-nowrap px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                        isActive
                          ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                          : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                      }`}
                    >
                      {item.label}
                    </a>
                  );
                })}
              </div>
              <button
                onClick={handleLogout}
                className="ml-4 px-3 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              >
                Log out
              </button>
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden bg-white dark:bg-gray-800">
            {children}
          </div>
        </div>

        {/* Desktop Layout */}
        <div className="hidden lg:flex flex-1 min-h-0 h-full overflow-hidden p-4 gap-4">
          <div className="w-64 flex-shrink-0 flex flex-col bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden shadow-md min-h-0 h-full">
            <UserSidebar />
          </div>
          <div className="flex-1 flex flex-col min-h-0 h-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden">
            <div className="flex-1 min-h-0 overflow-hidden">
              {children}
            </div>
          </div>
        </div>
      </div>
    </RequireAuth>
  );
}


