"use client";

import {
  useEffect,
  useId,
  type ReactNode,
} from "react";

/* ------------------------------------------------------------------ badges */

export type Tone = "neutral" | "gain" | "loss" | "warn" | "alert" | "brand" | "critical";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "border-edge bg-ink-800 text-mute",
  gain: "border-gain/30 bg-gain/10 text-gain",
  loss: "border-loss/30 bg-loss/10 text-loss",
  warn: "border-warn/30 bg-warn/10 text-warn",
  alert: "border-alert/30 bg-alert/10 text-alert",
  brand: "border-brand/30 bg-brand/10 text-brand-soft",
  critical: "border-loss/40 bg-loss/15 text-loss",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return <span className={`chip ${TONE_CLASS[tone]} ${className}`}>{children}</span>;
}

export function RiskBadge({ risk }: { risk: string }) {
  if (risk === "FLAGGED") return <Badge tone="warn">Flagged</Badge>;
  return <Badge tone="gain">Clear</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "EXECUTED"
      ? "gain"
      : status === "PENDING"
        ? "warn"
        : status === "FLAGGED"
          ? "alert"
          : status === "ORDER_BLOCKED"
            ? "critical"
            : "neutral";
  return <Badge tone={tone}>{status.replace(/_/g, " ")}</Badge>;
}

export function SideBadge({ side }: { side: string }) {
  return side === "BUY" ? (
    <Badge tone="gain">Buy</Badge>
  ) : (
    <Badge tone="loss">Sell</Badge>
  );
}

/* ------------------------------------------------------------------- cards */

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-edge/70 px-5 py-4">
          <div>
            {title && <h2 className="text-base font-semibold text-text">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-mute">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
}) {
  const accent: Record<Tone, string> = {
    neutral: "text-text",
    gain: "text-gain",
    loss: "text-loss",
    warn: "text-warn",
    alert: "text-alert",
    brand: "text-brand-soft",
    critical: "text-loss",
  };
  return (
    <div className="card-pad animate-fade-up">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-mute">{label}</p>
      <p className={`num mt-2 text-2xl font-semibold ${accent[tone]}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-mute">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ states */

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-mute">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
      {label ?? "Loading>>"}
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-5">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-9 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-1 px-6 py-12 text-center">
      <p className="text-sm font-medium text-text">{title}</p>
      {hint && <p className="max-w-sm text-xs text-mute">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss sm:flex-row sm:items-center sm:justify-between">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn-ghost btn-xs" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ tables */

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  onRowClick,
  emptyTitle = "Nothing to show",
  emptyHint,
}: {
  columns: Column<T>[];
  rows: T[] | null;
  rowKey: (row: T) => string;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: string;
}) {
  if (loading && !rows) return <TableSkeleton />;
  if (!rows || rows.length === 0)
    return <EmptyState title={emptyTitle} hint={emptyHint} />;

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.align === "right" ? "text-right" : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? "cursor-pointer" : undefined}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={
                    column.align === "right"
                      ? `text-right ${column.className ?? ""}`
                      : column.className
                  }
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------- modal */

export function Modal({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  width = "max-w-lg",
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-950/80 p-4 backdrop-blur-sm sm:items-center">
      <div
        className={`animate-fade-up card w-full ${width} shadow-glow`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="flex items-start justify-between gap-4 border-b border-edge/70 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-mute">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-mute transition hover:bg-ink-800 hover:text-text"
            aria-label="Close"
          >
            ?
          </button>
        </header>
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-edge/70 px-5 py-4">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ charts */

export function AreaChart({
  values,
  labels,
  height = 150,
  tone = "#4f7cff",
}: {
  values: number[];
  labels?: string[];
  height?: number;
  tone?: string;
}) {
  const gradientId = useId().replace(/:/g, "");
  if (values.length < 2)
    return (
      <p className="px-5 py-10 text-center text-xs text-mute">
        Not enough data points to draw a trend yet.
      </p>
    );

  const width = 720;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 8;
  const stepX = (width - pad * 2) / (values.length - 1);
  const toY = (value: number) =>
    height - pad - ((value - min) / span) * (height - pad * 2);

  const points = values.map((value, index) => {
    const x = pad + index * stepX;
    const y = toY(value);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const line = `M${points.join(" L")}`;
  const area = `${line} L${(pad + (values.length - 1) * stepX).toFixed(1)},${height - pad} L${pad},${height - pad} Z`;
  const last = points[points.length - 1].split(",");

  return (
    <div className="px-2 pb-2 pt-4">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label="Trend chart"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={tone} stopOpacity="0.35" />
            <stop offset="100%" stopColor={tone} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${gradientId})`} />
        <path
          d={line}
          fill="none"
          stroke={tone}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle cx={last[0]} cy={last[1]} r="4" fill={tone} />
      </svg>
      {labels && labels.length > 0 && (
        <div className="flex justify-between px-2 text-[11px] text-mute">
          <span>{labels[0]}</span>
          <span>{labels[labels.length - 1]}</span>
        </div>
      )}
    </div>
  );
}

export function AllocationBar({
  value,
  total,
  tone = "#4f7cff",
}: {
  value: number;
  total: number;
  tone?: string;
}) {
  const ratio = total > 0 ? Math.min(100, Math.max(0, (value / total) * 100)) : 0;
  return (
    <div className="h-1.5 w-full rounded-full bg-ink-800">
      <div
        className="h-1.5 rounded-full transition-all"
        style={{ width: `${ratio}%`, background: tone }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ fields */

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-[11px] text-mute">{hint}</span>}
      {error && <span className="mt-1 block text-[11px] text-loss">{error}</span>}
    </label>
  );
}
