"use client";

import { useMemo, useState } from "react";
import { RequireAdmin } from "@/components/require-admin";
import {
  Badge,
  Card,
  DataTable,
  ErrorNote,
  StatusBadge,
  type Column,
  type Tone,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";
import type { BlockedOrderRow, Paged } from "@/lib/types";

const SEVERITY_TONE: Record<string, Tone> = {
  critical: "critical",
  high: "loss",
  medium: "warn",
  low: "neutral",
};

function BlockedContent() {
  const [outcome, setOutcome] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const path = useMemo(() => {
    const params = new URLSearchParams({ limit: "200" });
    if (outcome) params.set("outcome", outcome);
    return `/security/blocked-orders?${params.toString()}`;
  }, [outcome]);

  const blocked = useApi<Paged<BlockedOrderRow>>(path);

  const rows = useMemo(() => {
    const items = blocked.data?.items ?? [];
    if (!outcome) return items;
    return items.filter((row) => row.event_type === outcome);
  }, [blocked.data, outcome]);

  const columns: Column<BlockedOrderRow>[] = [
    {
      key: "when",
      header: "Detected",
      render: (row) => (
        <button
          type="button"
          className="num text-xs text-brand-soft hover:underline"
          onClick={() => setExpanded((current) => (current === row.event_id ? null : row.event_id))}
        >
          {dateTime(row.detected_at)}
        </button>
      ),
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (row) => <StatusBadge status={row.event_type} />,
    },
    {
      key: "severity",
      header: "Severity",
      render: (row) => (
        <Badge tone={SEVERITY_TONE[row.severity] ?? "neutral"}>{row.severity}</Badge>
      ),
    },
    {
      key: "attempt",
      header: "Attempted order",
      render: (row) => (
        <div>
          <p className="num text-xs">
            {row.attempted_side} {row.attempted_order_type}
          </p>
          <p className="num text-[11px] text-mute">
            qty {row.attempted_quantity ?? "--"}
            {row.attempted_limit_price ? ` * limit ${money(row.attempted_limit_price)}` : ""}
          </p>
        </div>
      ),
    },
    {
      key: "indicator",
      header: "Matched indicator",
      render: (row) => (
        <div>
          <p className="num text-xs">{row.indicator_value ?? "--"}</p>
          <p className="text-[11px] text-mute">
            {row.indicator_type ?? "--"} * {row.threat_category ?? "--"} * confidence{" "}
            {row.confidence ?? "--"}
          </p>
        </div>
      ),
    },
    {
      key: "source",
      header: "Source",
      render: (row) => <span className="text-xs text-mute">{row.source_name ?? "--"}</span>,
    },
    {
      key: "origin",
      header: "Origin",
      render: (row) => <span className="num text-xs">{row.origin_ip ?? "--"}</span>,
    },
    {
      key: "order",
      header: "Order row",
      render: (row) =>
        row.order_id ? (
          <span className="num text-[11px] text-mute">created</span>
        ) : (
          <Badge tone="critical">never written</Badge>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <Card
        title="Blocked & flagged orders"
        subtitle="Blocked attempts never created an order row -- the evidence is reconstructed from security_events"
        action={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setOutcome("")}
              className={`btn btn-xs ${outcome === "" ? "bg-brand/15 text-brand-soft ring-1 ring-brand/40" : "bg-ink-850 text-mute"}`}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setOutcome("ORDER_BLOCKED")}
              className={`btn btn-xs ${outcome === "ORDER_BLOCKED" ? "bg-loss/15 text-loss ring-1 ring-loss/40" : "bg-ink-850 text-mute"}`}
            >
              Blocked
            </button>
            <button
              type="button"
              onClick={() => setOutcome("ORDER_FLAGGED")}
              className={`btn btn-xs ${outcome === "ORDER_FLAGGED" ? "bg-warn/15 text-warn ring-1 ring-warn/40" : "bg-ink-850 text-mute"}`}
            >
              Flagged
            </button>
          </div>
        }
      >
        {blocked.error ? (
          <div className="p-5">
            <ErrorNote message={blocked.error.message} onRetry={blocked.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            loading={blocked.loading}
            rowKey={(row) => row.event_id}
            emptyTitle="No blocked or flagged orders"
            emptyHint="Try an order from the seeded C2 address 198.51.100.66 to trigger a block."
          />
        )}
      </Card>

      {expanded && (
        <Card title="Event payload" subtitle={expanded}>
          <pre className="max-h-96 overflow-auto rounded-xl bg-ink-950/70 p-4 text-xs text-mute">
            {JSON.stringify(
              (blocked.data?.items ?? []).find((row) => row.event_id === expanded)?.details ?? {},
              null,
              2,
            )}
          </pre>
        </Card>
      )}
    </div>
  );
}

export default function BlockedOrdersPage() {
  return (
    <RequireAdmin>
      <BlockedContent />
    </RequireAdmin>
  );
}
