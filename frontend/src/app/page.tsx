'use client';

import Link from 'next/link';
import { Sidebar, TopBar, MacroTicker, DisclaimerBanner } from '@/components/layout/Sidebar';
import { useStockStore } from '@/store';

export default function HomePage() {
  const { selectedTicker } = useStockStore();
  const ticker = (selectedTicker || 'AAPL').toUpperCase();

  return (
    <div className="flex h-screen bg-surface-0 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar />
        <MacroTicker />
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <DisclaimerBanner />
          <div className="card p-6">
            <h1 className="text-xl font-bold text-text-bright">QuantEdge AI</h1>
            <p className="text-sm text-text-muted mt-2">
              Başlamak için bir ticker seçin.
            </p>
            <div className="mt-4">
              <Link className="btn-primary inline-flex" href={`/stock/${ticker}`}>
                {ticker} sayfasına git
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

