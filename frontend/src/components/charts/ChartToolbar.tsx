'use client';

import { Settings, Maximize2, Minimize2 } from 'lucide-react';

import { useChartStore } from '@/store';

export function ChartToolbar({
  isFullscreen,
  onToggleFullscreen,
}: {
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}) {
  const { chartSettings, toggleSetting } = useChartStore();

  return (
    <div className="flex items-center gap-2">
      <button
        className="btn-ghost px-2 py-1.5 text-xs"
        onClick={() => toggleSetting('showBollingerBands')}
        title="Bollinger"
      >
        <Settings size={14} />
        BB
      </button>
      <button
        className="btn-ghost px-2 py-1.5 text-xs"
        onClick={onToggleFullscreen}
        title="Tam ekran"
      >
        {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
      <div className="hidden md:flex items-center gap-2 ml-2">
        <label className="text-[10px] text-text-muted flex items-center gap-1">
          <input
            type="checkbox"
            checked={chartSettings.showSMA20}
            onChange={() => toggleSetting('showSMA20')}
          />
          SMA20
        </label>
        <label className="text-[10px] text-text-muted flex items-center gap-1">
          <input
            type="checkbox"
            checked={chartSettings.showSMA50}
            onChange={() => toggleSetting('showSMA50')}
          />
          SMA50
        </label>
        <label className="text-[10px] text-text-muted flex items-center gap-1">
          <input
            type="checkbox"
            checked={chartSettings.showVWAP}
            onChange={() => toggleSetting('showVWAP')}
          />
          VWAP
        </label>
      </div>
    </div>
  );
}

