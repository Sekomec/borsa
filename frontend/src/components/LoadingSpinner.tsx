'use client';

// ============================================================
// QuantEdge AI — Yeniden Kullanılabilir UI Bileşenleri
// ============================================================

import { motion } from 'framer-motion';
import { AlertTriangle, CheckCircle, Info, XCircle, X } from 'lucide-react';
import type { ReactNode } from 'react';

// ----------------------------------------------------------
// Loading Spinner
// ----------------------------------------------------------

interface LoadingSpinnerProps {
  size?:  'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

export function LoadingSpinner({ size = 'md', label, className = '' }: LoadingSpinnerProps) {
  const sizeMap = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' };
  const borderMap = { sm: 'border-2', md: 'border-2', lg: 'border-3' };

  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <div
        className={`${sizeMap[size]} ${borderMap[size]} rounded-full
          border-accent-cyan border-t-transparent animate-spin`}
      />
      {label && (
        <p className="text-xs text-text-muted animate-pulse">{label}</p>
      )}
    </div>
  );
}

// ----------------------------------------------------------
// Skeleton Loader
// ----------------------------------------------------------

interface SkeletonProps {
  className?: string;
  rows?: number;
  rowClassName?: string;
}

export function Skeleton({ className = '', rows, rowClassName = '' }: SkeletonProps) {
  if (rows) {
    return (
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className={`skeleton h-4 w-full ${rowClassName}`} />
        ))}
      </div>
    );
  }
  return <div className={`skeleton ${className}`} />;
}

export function CardSkeleton() {
  return (
    <div className="card p-4 space-y-3">
      <Skeleton className="h-5 w-32" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-4/5" />
      <Skeleton className="h-3 w-3/5" />
    </div>
  );
}

// ----------------------------------------------------------
// Alert / Toast
// ----------------------------------------------------------

type AlertType = 'info' | 'success' | 'warning' | 'error';

interface AlertProps {
  type:     AlertType;
  title?:   string;
  message:  string;
  onClose?: () => void;
  className?: string;
}

export function Alert({ type, title, message, onClose, className = '' }: AlertProps) {
  const config = {
    info:    { icon: Info,          color: 'text-blue-400',   bg: 'bg-blue-400/5',   border: 'border-blue-400/20'   },
    success: { icon: CheckCircle,   color: 'text-bull',       bg: 'bg-bull/5',       border: 'border-bull/20'       },
    warning: { icon: AlertTriangle, color: 'text-amber-400',  bg: 'bg-amber-400/5',  border: 'border-amber-400/20'  },
    error:   { icon: XCircle,       color: 'text-bear',       bg: 'bg-bear/5',       border: 'border-bear/20'       },
  };

  const { icon: Icon, color, bg, border } = config[type];

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className={`flex items-start gap-3 p-3 rounded-xl border ${bg} ${border} ${className}`}
    >
      <Icon size={14} className={`${color} mt-0.5 flex-shrink-0`} />
      <div className="flex-1 min-w-0">
        {title && (
          <p className={`text-xs font-semibold ${color} mb-0.5`}>{title}</p>
        )}
        <p className={`text-xs ${color} opacity-80`}>{message}</p>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className={`${color} opacity-60 hover:opacity-100 transition-opacity flex-shrink-0`}
        >
          <X size={12} />
        </button>
      )}
    </motion.div>
  );
}

// ----------------------------------------------------------
// Badge
// ----------------------------------------------------------

interface BadgeProps {
  variant?: 'bull' | 'bear' | 'neutral' | 'cyan' | 'purple' | 'amber';
  size?:    'sm' | 'md';
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'neutral', size = 'md', children, className = '' }: BadgeProps) {
  const variantMap = {
    bull:    'badge-bull',
    bear:    'badge-bear',
    neutral: 'badge-neutral',
    cyan:    'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20 border',
    purple:  'bg-purple-500/10 text-purple-400 border-purple-500/20 border',
    amber:   'bg-amber-400/10 text-amber-400 border-amber-400/20 border',
  };

  const sizeMap = {
    sm: 'text-[9px] px-1.5 py-0.5',
    md: 'text-xs px-2 py-0.5',
  };

  return (
    <span className={`badge ${variantMap[variant]} ${sizeMap[size]} ${className}`}>
      {children}
    </span>
  );
}

// ----------------------------------------------------------
// Metric Card
// ----------------------------------------------------------

interface MetricCardProps {
  label:       string;
  value:       string | number | null | undefined;
  subLabel?:   string;
  trend?:      'up' | 'down' | 'neutral';
  prefix?:     string;
  suffix?:     string;
  highlight?:  boolean;
  className?:  string;
}

export function MetricCard({
  label, value, subLabel, trend, prefix = '', suffix = '',
  highlight, className = '',
}: MetricCardProps) {
  const trendColor = trend === 'up' ? 'text-bull' : trend === 'down' ? 'text-bear' : 'text-text-primary';

  return (
    <div className={`metric-box card-hover ${highlight ? 'border-accent-cyan/20 bg-accent-gradient' : ''} ${className}`}>
      <span className="metric-label">{label}</span>
      {value !== undefined && value !== null ? (
        <span className={`metric-value ${trendColor}`}>
          {prefix}{typeof value === 'number' ? value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : value}{suffix}
        </span>
      ) : (
        <span className="metric-value text-text-muted">—</span>
      )}
      {subLabel && <span className="text-[10px] text-text-muted">{subLabel}</span>}
    </div>
  );
}

// ----------------------------------------------------------
// Empty State
// ----------------------------------------------------------

interface EmptyStateProps {
  emoji?:    string;
  title:     string;
  subtitle?: string;
  action?:   ReactNode;
  className?: string;
}

export function EmptyState({ emoji = '📭', title, subtitle, action, className = '' }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-12 px-4 text-center ${className}`}>
      <span className="text-4xl">{emoji}</span>
      <div>
        <p className="font-semibold text-text-primary">{title}</p>
        {subtitle && <p className="text-sm text-text-muted mt-1">{subtitle}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

// ----------------------------------------------------------
// Progress Bar
// ----------------------------------------------------------

interface ProgressBarProps {
  value:     number;   // 0-100
  max?:      number;
  color?:    string;
  showLabel?: boolean;
  label?:    string;
  height?:   'sm' | 'md';
}

export function ProgressBar({
  value, max = 100, color, showLabel, label, height = 'md',
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const barColor = color || (pct > 66 ? '#10B981' : pct > 33 ? '#F59E0B' : '#EF4444');
  const heightClass = height === 'sm' ? 'h-1' : 'h-1.5';

  return (
    <div className="w-full">
      {(showLabel || label) && (
        <div className="flex justify-between text-xs text-text-muted mb-1">
          <span>{label}</span>
          <span className="font-mono" style={{ color: barColor }}>{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className={`score-bar ${heightClass}`}>
        <motion.div
          className="score-bar-fill"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          style={{ backgroundColor: barColor }}
        />
      </div>
    </div>
  );
}

// ----------------------------------------------------------
// Divider
// ----------------------------------------------------------

export function Divider({ label }: { label?: string }) {
  if (!label) return <div className="border-t border-border-subtle" />;

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 border-t border-border-subtle" />
      <span className="text-[10px] text-text-muted uppercase tracking-widest">{label}</span>
      <div className="flex-1 border-t border-border-subtle" />
    </div>
  );
}

// ----------------------------------------------------------
// Tooltip wrapper (CSS-only)
// ----------------------------------------------------------

interface TooltipProps {
  content:  string;
  children: ReactNode;
  position?: 'top' | 'bottom';
}

export function Tooltip({ content, children, position = 'top' }: TooltipProps) {
  return (
    <div className="relative group inline-flex">
      {children}
      <div
        className={`
          absolute z-50 px-2 py-1 rounded-lg bg-surface-4 border border-border-default
          text-[10px] text-text-primary whitespace-nowrap pointer-events-none
          opacity-0 group-hover:opacity-100 transition-opacity duration-150
          ${position === 'top' ? 'bottom-full mb-1.5 left-1/2 -translate-x-1/2' : 'top-full mt-1.5 left-1/2 -translate-x-1/2'}
        `}
      >
        {content}
      </div>
    </div>
  );
}
