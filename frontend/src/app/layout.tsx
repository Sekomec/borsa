import '../styles/globals.css';
import type { ReactNode } from 'react';

export const metadata = {
  title: 'QuantEdge AI',
  description: 'QuantEdge AI Dashboard',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}

