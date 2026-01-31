"use client";

import { useEffect, useState } from 'react';
import { getCumulativeDailyPapers, type CumulativeDailyPaperItem } from '../../../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import Link from 'next/link';

/**
 * Papers Overview Page
 * 
 * Displays a cumulative graph showing total papers per day from the first paper to today.
 * The cumulative count shows the running total (e.g., if 10 papers yesterday and 5 today, today shows 15).
 */
export default function PapersOverviewPage() {
  const [data, setData] = useState<CumulativeDailyPaperItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await getCumulativeDailyPapers();
        setData(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  /**
   * Format date for display in chart
   */
  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  /**
   * Custom tooltip formatter
   */
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-3 shadow-lg">
          <p className="font-semibold">{formatDate(data.date)}</p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Daily: <span className="font-medium">{data.dailyCount}</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Total: <span className="font-medium">{data.cumulativeCount}</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Processed: <span className="font-medium">{data.cumulativeProcessed}</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Failed: <span className="font-medium">{data.cumulativeFailed}</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Processing: <span className="font-medium">{data.cumulativeProcessing}</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Not Started: <span className="font-medium">{data.cumulativeNotStarted}</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="px-6 py-6 text-gray-900 dark:text-gray-100">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Papers Overview</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Cumulative total papers from first paper to today
          </p>
        </div>
        <Link
          href="/management"
          className="px-4 py-2 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
        >
          Back to Management
        </Link>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center h-96">
          <div>Loading…</div>
        </div>
      ) : data.length === 0 ? (
        <div className="flex items-center justify-center h-96">
          <div className="text-gray-500 dark:text-gray-400">No data available</div>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm p-6">
          <ResponsiveContainer width="100%" height={500}>
            <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" className="dark:stroke-gray-700" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                stroke="#6b7280"
                className="dark:stroke-gray-400"
                angle={-45}
                textAnchor="end"
                height={100}
                interval="preserveStartEnd"
              />
              <YAxis
                stroke="#6b7280"
                className="dark:stroke-gray-400"
                label={{ value: 'Total Papers', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Line
                type="monotone"
                dataKey="cumulativeCount"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="Total"
              />
              <Line
                type="monotone"
                dataKey="cumulativeFailed"
                stroke="#fca5a5"
                strokeWidth={2}
                dot={false}
                name="Failed"
              />
              <Line
                type="monotone"
                dataKey="cumulativeProcessed"
                stroke="#4ade80"
                strokeWidth={2}
                dot={false}
                name="Processed"
              />
              <Line
                type="monotone"
                dataKey="cumulativeNotStarted"
                stroke="#d1d5db"
                strokeWidth={2}
                dot={false}
                name="Not Started"
              />
              <Line
                type="monotone"
                dataKey="cumulativeProcessing"
                stroke="#f97316"
                strokeWidth={2}
                dot={false}
                name="Processing"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

