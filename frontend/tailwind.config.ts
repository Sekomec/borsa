import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'surface-0': '#0B0F14',
        'surface-1': '#0D1117',
        'surface-2': '#101826',
        'surface-3': '#111B2B',
        'surface-4': '#162033',
        'text-muted': '#4B5980',
        'text-secondary': '#A7B3D1',
        'text-primary': '#D7E0FF',
        'text-bright': '#F4F7FF',
        'border-subtle': '#1E2535',
        'border-default': '#2A3550',
        'border-strong': '#334266',
        'accent-cyan': '#00D4FF',
        bull: '#10B981',
        bear: '#EF4444',
        neutral: '#6B7280'
      }
    }
  },
  plugins: []
} satisfies Config;

