'use client';

import React from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { authClient } from '../services/auth';

type SidebarItem = {
  href: string;
  label: string;
};

const ITEMS: SidebarItem[] = [
  { href: '/user/list', label: 'My list' },
  { href: '/user/requests', label: 'My requests' },
  // Future: { href: '/user/settings', label: 'Settings' },
];

export default function UserSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const handleLogout = async () => {
    try {
      await authClient.signOut();
    } catch {}
    router.replace('/');
  };
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold">User</h2>
      </div>
      <nav className="flex-1 min-h-0 overflow-y-auto">
        <ul className="p-2 space-y-1">
          {ITEMS.map((item) => {
            const isActive = pathname?.startsWith(item.href);
            return (
              <li key={item.href}>
                <a
                  href={item.href}
                  className={`block w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700'
                  }`}
                >
                  {item.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-gray-200 dark:border-gray-700 p-2">
        <button
          onClick={handleLogout}
          className="w-full text-left px-3 py-2 rounded-md text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200"
        >
          Log out
        </button>
      </div>
    </div>
  );
}


