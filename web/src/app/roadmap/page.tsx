import React from 'react';

export default function RoadmapPage() {
  return (
    <main className="w-full">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
        <h1 className="text-3xl font-bold">Roadmap</h1>

        <section className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h2 className="text-xl font-semibold mb-2">Phase 1: An open source foundation</h2>
          <p className="text-gray-700 dark:text-gray-300">
            Establish a solid, transparent base. We will rely on donations to get things going.
          </p>
        </section>

        <section className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h2 className="text-xl font-semibold mb-2">Phase 2: Core systems</h2>
          <p className="text-gray-700 dark:text-gray-300 mb-3">
            Build the essential features that make the product useful day-to-day:
          </p>
          <ul className="list-disc pl-5 space-y-1 text-gray-700 dark:text-gray-300">
            <li>Similar papers</li>
            <li>Search</li>
            <li>Automatic prioritization to decide which papers get indexed</li>
          </ul>
        </section>

        <section className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h2 className="text-xl font-semibold mb-2">Phase 3: Advanced tools for those who need it</h2>
          <p className="text-gray-700 dark:text-gray-300">
            Power-user capabilities and workflows for a monthly subscription. Papers will always be freely accessible. Our goal here is to make a solid, self-sustaining product, such that we can keep the core service free for everyone.
          </p>
        </section>
      </div>
    </main>
  );
}


