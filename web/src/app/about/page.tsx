import React from 'react';

export default function AboutPage() {
  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h1 className="text-3xl font-bold mb-3">About Us</h1>
          <p className="text-gray-700 dark:text-gray-300">
            Our mission is to make research papers comprehensible for people without a PhD.
          </p>
          <div className="mt-6 text-sm text-gray-500 dark:text-gray-400">
            This page is a placeholder. More details are coming soon.
          </div>
        </div>
      </div>
    </main>
  );
}


