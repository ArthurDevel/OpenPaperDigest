'use client';

import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * Theme toggle switch component
 * Manages dark/light mode state and persists to localStorage
 * @returns Toggle switch for switching between light and dark themes
 */
export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem('theme');
    const shouldBeDark = stored === 'dark';
    setIsDark(shouldBeDark);
    applyTheme(shouldBeDark);
  }, []);

  /**
   * Applies theme to document
   * @param dark - Whether to apply dark theme
   */
  const applyTheme = (dark: boolean): void => {
    if (dark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  /**
   * Toggles theme and saves to localStorage
   */
  const toggleTheme = (): void => {
    const newIsDark = !isDark;
    setIsDark(newIsDark);
    localStorage.setItem('theme', newIsDark ? 'dark' : 'light');
    applyTheme(newIsDark);
  };

  if (!mounted) {
    return (
      <div className="w-14 h-7 rounded-full border border-gray-300 dark:border-gray-700" />
    );
  }

  return (
    <button
      onClick={toggleTheme}
      className="relative inline-flex items-center w-14 h-7 rounded-full border border-gray-300 dark:border-gray-600 bg-gray-200 dark:bg-gray-700 transition-colors hover:bg-gray-300 dark:hover:bg-gray-600"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span
        className={`inline-flex items-center justify-center w-6 h-6 rounded-full bg-white dark:bg-gray-800 shadow-md transform transition-transform ${
          isDark ? 'translate-x-7' : 'translate-x-0.5'
        }`}
      >
        {isDark ? (
          <Moon size={14} className="text-gray-700 dark:text-gray-300" />
        ) : (
          <Sun size={14} className="text-gray-700" />
        )}
      </span>
    </button>
  );
}

