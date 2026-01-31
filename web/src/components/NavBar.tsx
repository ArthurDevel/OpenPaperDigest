'use client';

import Link from 'next/link';
import Image from 'next/image';
import React, { useState } from 'react';
import { Github, User as UserIcon, X, Menu } from 'lucide-react';
import { useSession } from '@/services/auth';
import ThemeToggle from './ThemeToggle';

type NavBarProps = {
  className?: string;
};

/**
 * Navigation bar component with responsive mobile menu
 * @param className - Additional CSS classes to apply
 * @returns Navigation bar with hamburger menu for mobile
 */
export default function NavBar({ className = '' }: NavBarProps) {
  const { user } = useSession();
  const isLoggedIn = Boolean(user?.id);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  /**
   * Toggles the mobile menu open/closed state
   */
  const toggleMobileMenu = (): void => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  /**
   * Closes the mobile menu
   */
  const closeMobileMenu = (): void => {
    setIsMobileMenuOpen(false);
  };
  return (
    <nav className={`w-full ${className}`}>
      <div className="w-full px-4 sm:px-6 lg:px-10 pt-7 pb-3 flex items-center justify-between">
        <Link href="/" className="flex flex-col">
          <div className="flex items-center gap-2">
            <Image
              src="/opdlogo.svg"
              alt="Open Paper Digest Logo"
              width={32}
              height={32}
              className="w-8 h-8"
            />
            <span className="text-base font-semibold text-gray-900 dark:text-gray-100">Open Paper Digest</span>
          </div>
          <span className="text-sm text-gray-600 dark:text-gray-400">Doomscrolling for Smart People</span>
        </Link>

        <ul className="hidden md:flex items-center gap-6">
          <li>
            <Link href="/" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Papers Feed
            </Link>
          </li>
          {/*<li>
            <Link href="/donate" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Donate Inference
            </Link>
          </li>
          <li>
            <Link href="/roadmap" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Roadmap
            </Link>
          </li>
          <li>
            <Link href="/about" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              About Us
            </Link>
          </li>*/}
          <li>
            <Link
              href="https://github.com/ArthurDevel/papersummarizertool"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors flex items-center gap-2"
            >
              <Github size={16} />
              <span>Star us on GitHub</span>
            </Link>
          </li>
        </ul>

        <div className="flex items-center gap-3">
          <div className="hidden md:block">
            <ThemeToggle />
          </div>
          {isLoggedIn ? (
            <Link
              href="/user"
              className="inline-flex items-center justify-center w-9 h-9 rounded-full border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              title="Your account"
              aria-label="Your account"
            >
              <UserIcon size={18} />
            </Link>
          ) : (
            <Link
              href="/login"
              className="px-3 py-1.5 rounded-md text-sm border border-gray-300 dark:border-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              Log in
            </Link>
          )}
          <div className="md:hidden">
            <button
              type="button"
              onClick={toggleMobileMenu}
              aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
              className="inline-flex items-center justify-center p-2 rounded-md text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors"
            >
              {isMobileMenuOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          <div className="px-4 py-4">
            <nav className="space-y-3 text-center">
              <Link
                href="/"
                onClick={closeMobileMenu}
                className="block py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                Papers Feed
              </Link>
              <Link
                href="https://github.com/ArthurDevel/papersummarizertool"
                target="_blank"
                rel="noopener noreferrer"
                onClick={closeMobileMenu}
                className="flex items-center justify-center gap-2 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                <Github size={16} />
                <span>Star us on GitHub</span>
              </Link>
              <div className="flex items-center justify-center gap-2 py-2">
                <span className="text-sm text-gray-700 dark:text-gray-300">Theme:</span>
                <ThemeToggle />
              </div>
              {isLoggedIn ? (
                <Link
                  href="/user"
                  onClick={closeMobileMenu}
                  className="flex items-center justify-center gap-2 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
                >
                  <UserIcon size={16} />
                  <span>Your account</span>
                </Link>
              ) : (
                <Link
                  href="/login"
                  onClick={closeMobileMenu}
                  className="block py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
                >
                  Log in
                </Link>
              )}
            </nav>
          </div>
        </div>
      )}
    </nav>
  );
}
