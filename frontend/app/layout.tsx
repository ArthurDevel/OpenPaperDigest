import './globals.css';
import NavBar from '../components/NavBar';
import Footer from '../components/Footer';
import UmamiScript from '../components/UmamiScript';
import { Suspense } from 'react';
import 'katex/dist/katex.min.css';

export const metadata = {
  title: {
    default: 'Open Paper Digest - Daily Research Papers Without a PhD',
    template: '%s | Open Paper Digest'
  },
  description: 'Daily digest of popular research papers made accessible for everyone. Stay up to date with advanced research through a continuous feed of digestible paper summaries.',
  keywords: ['research papers', 'daily digest', 'paper summaries', 'academic research', 'arxiv', 'scientific papers', 'research feed'],
  authors: [{ name: 'Open Paper Digest' }],
  creator: 'Open Paper Digest',
  publisher: 'Open Paper Digest',
  openGraph: {
    type: 'website',
    locale: 'en_US',
    siteName: 'Open Paper Digest',
    title: 'Open Paper Digest - Daily Research Papers Without a PhD',
    description: 'Daily digest of popular research papers made accessible for everyone. Stay up to date with advanced research through a continuous feed of digestible paper summaries.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Open Paper Digest - Daily Research Papers Without a PhD',
    description: 'Daily digest of popular research papers made accessible for everyone. Stay up to date with advanced research through a continuous feed of digestible paper summaries.',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
        <UmamiScript />
        <div className="flex flex-col min-h-screen">
          <NavBar />
          <Suspense fallback={<div className="flex-1 min-h-0" />}>
            <div className="flex-1 min-h-0">{children}</div>
          </Suspense>
          <Footer />
        </div>
      </body>
    </html>
  )
}
