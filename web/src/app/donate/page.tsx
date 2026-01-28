import React from 'react';

export default function DonatePage() {
  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h1 className="text-3xl font-bold mb-3">Donate Inference</h1>
          <p className="text-gray-700 dark:text-gray-300 mb-4">
            We use frontier large language models to analyze research papers and make them more comprehensible for everyone. Running these models requires significant compute.
          </p>
          <p className="text-gray-700 dark:text-gray-300 mb-4">
            In the future, you&#39;ll be able to donate an OpenRouter API key to help fund this computation. If you choose, you&#39;ll also be able to provide a list of papers you&#39;d like us to prioritize using your key.
          </p>
          <div className="mt-6 text-sm text-gray-500 dark:text-gray-400">
            This page is a placeholder. More details and contribution options are coming soon.
          </div>
        </div>
      </div>
    </main>
  );
}


