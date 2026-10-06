"use client";

import Link from "next/link";
import { RequireAdmin } from "@/components/require-admin";
import {
  Badge,
  Card,
  DataTable,
  ErrorNote,
  StatCard,
  StatusBadge,
  type Column,
  type Tone,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateTime, relative } from "@/lib/format";
import type { BlockedOrderRow, SecurityDashboard, SecurityEventRow, ThreatSource } from "@/lib/types";

const SEVERITY_TONE: Record<string, Tone> = {
  critical: "critical",
  high: "loss",
  medium: "warn",
  low: "neutral",
};

function DashboardContent() {
  const dashboard = useApi<SecurityDashboard>("/security/dashboard");
  const events = useApi<SecurityEventRow[]>("/security/events?limit=10");
  const sources = useApi<ThreatSource[]>("/security/sources");
  const blocked = useApi<{ items: BlockedOrderRow[]; total: number }>(
    "/security/blocked-orders?limit=6",
  );

  const recentColumns: Column<SecurityEventRow>[] = [
    {
      key: "when",
      header: "When",
      render: (row) => (
        <div>
          <p className="num text-xs">{dateTime(row.created_at)}</p>
          <p className="text-[11px] text-mute">{relative(row.created_at)}</p>
        </div>
      ),
    },
    {
      key: "type",
      header: "Event",
      render: (row) => <Badge tone={SEVERITY_TONE[row.severity] ?? "neutral"}>{row.event_type}</Badge>,
    },
    {
      key: "indicator",
      header: "Indicator",
      render: (row) =>
        row.indicator_value ? (
          <div>
            <p className="num text-xs">{row.indicator_value}</p>
            <p className="text-[11px] text-mute">
              {row.indicator_type} * confidence {row.confidence ?? "--"}
            </p>
          </div>
        ) : (
          <span className="text-xs text-mute">--</span>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      {dashboard.error && (
        <ErrorNote message={dashboard.error.message} onRetry={dashboard.reload} />
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Active threats"
          value={dashboard.data?.active_threats ?? 0}
          sub={`${dashboard.data?.critical_threats ?? 0} critical (confidence ? 80)`}
          tone="alert"
        />
        <StatCard
          label="Blocked orders"
          value={dashboard.data?.blocked_orders_total ?? 0}
          sub={`${dashboard.data?.blocked_orders_24h ?? 0} in the last 24h`}
          tone="loss"
        />
        <StatCard
          label="Flagged orders"
          value={dashboard.data?.flagged_orders_total ?? 0}
          sub="Confidence 60-79, still executed"
          tone="warn"
        />
        <StatCard
          label="Security events (24h)"
          value={dashboard.data?.events_24h ?? 0}
          sub={`${dashboard.data?.audit_entries ?? 0} audit entries total`}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Recent security events"
          subtitle="Live feed from the security_events table"
          action={
            <Link href="/admin/audit" className="btn-ghost btn-xs">
              Audit logs
            </Link>
          }
        >
          <DataTable
            columns={recentColumns}
            rows={events.data}
            loading={events.loading}
            rowKey={(row) => row.event_id}
            emptyTitle="No events recorded"
            emptyHint="Blocked and flagged orders will appear here immediately."
          />
        </Card>

        <Card title="Threat sources" subtitle="Provenance of the indicators">
          {sources.error ? (
            <div className="p-5">
              <ErrorNote message={sources.error.message} onRetry={sources.reload} />
            </div>
          ) : (
            <ul className="space-y-3 p-5">
              {(sources.data ?? []).map((source) => (
                <li key={source.source_id} className="rounded-xl border border-edge bg-ink-850/50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium">{source.name}</p>
                    <Badge tone={source.reliability >= 4 ? "gain" : "neutral"}>
                      R{source.reliability}
                    </Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-mute">
                    {source.active_indicators} active * {source.indicator_count} total indicators
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card
        title="Blocked & flagged order attempts"
        subtitle="Rejected orders reconstructed from the security event log"
        action={
          <Link href="/admin/blocked" className="btn-ghost btn-xs">
            View all
          </Link>
        }
      >
        <DataTable
          columns={[
            {
              key: "when",
              header: "Detected",
              render: (row) => <span className="num text-xs">{dateTime(row.detected_at)}</span>,
            },
            {
              key: "type",
              header: "Outcome",
              render: (row) => <StatusBadge status={row.event_type} />,
            },
            {
              key: "attempt",
              header: "Attempted order",
              render: (row) => (
                <span className="num text-xs">
                  {row.attempted_side} {row.attempted_order_type} * {row.attempted_quantity ?? "--"}
                  {row.attempted_limit_price ? ` @ ${row.attempted_limit_price}` : ""}
                </span>
              ),
            },
            {
              key: "indicator",
              header: "Matched indicator",
              render: (row) => (
                <div>
                  <p className="num text-xs">{row.indicator_value ?? "--"}</p>
                  <p className="text-[11px] text-mute">
                    {row.threat_category ?? "--"} * confidence {row.confidence ?? "--"}
                  </p>
                </div>
              ),
            },
            {
              key: "severity",
              header: "Severity",
              render: (row) => (
                <Badge tone={SEVERITY_TONE[row.severity] ?? "neutral"}>{row.severity}</Badge>
              ),
            },
          ]}
          rows={blocked.data?.items ?? null}
          loading={blocked.loading}
          rowKey={(row) => row.event_id}
          emptyTitle="No blocked or flagged orders"
          emptyHint="Place an order from a seeded threat address to see the screening pipeline."
        />
      </Card>
    </div>
  );
}

export default function SecurityDashboardPage() {
  return (
    <RequireAdmin>
      <DashboardContent />
    </RequireAdmin>
  );
}
