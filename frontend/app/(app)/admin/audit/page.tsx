"use client";

import { useMemo, useState } from "react";
import { RequireAdmin } from "@/components/require-admin";
import { Badge, Card, DataTable, ErrorNote, type Column } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import type { AuditRow } from "@/lib/types";

const ACTIONS = [
  "REGISTER",
  "LOGIN",
  "LOGIN_FAILED",
  "ORDER_PLACED",
  "ORDER_EXECUTED",
  "ORDER_BLOCKED",
  "ORDER_UPDATED",
  "THREAT_CREATE",
  "THREAT_UPDATE",
  "THREAT_DISABLE",
  "SOURCE_CREATE",
];

function AuditContent() {
  const [action, setAction] = useState("");
  const [status, setStatus] = useState("");

  const path = useMemo(() => {
    const params = new URLSearchParams({ limit: "200" });
    if (action) params.set("action", action);
    if (status) params.set("status", status);
    return `/security/audit-logs?${params.toString()}`;
  }, [action, status]);

  const audit = useApi<AuditRow[]>(path);

  const columns: Column<AuditRow>[] = [
    {
      key: "when",
      header: "When",
      render: (row) => <span className="num text-xs">{dateTime(row.created_at)}</span>,
    },
    {
      key: "actor",
      header: "Actor",
      render: (row) =>
        row.actor_email ? (
          <div>
            <p className="text-xs">{row.actor_email}</p>
            <p className="text-[11px] text-mute">{row.actor_role ?? "--"}</p>
          </div>
        ) : (
          <div>
            <p className="text-xs text-mute">system</p>
            <p className="text-[11px] text-mute">{row.actor_role ?? "--"}</p>
          </div>
        ),
    },
    {
      key: "action",
      header: "Action",
      render: (row) => (
        <Badge
          tone={
            row.action.includes("BLOCKED") || row.action.includes("FAILED")
              ? "loss"
              : row.action.startsWith("THREAT") || row.action.startsWith("SOURCE")
                ? "alert"
                : "brand"
          }
        >
          {row.action}
        </Badge>
      ),
    },
    {
      key: "entity",
      header: "Entity",
      render: (row) => (
        <div>
          <p className="text-xs text-mute">{row.entity_type ?? "--"}</p>
          <p className="num text-[11px] text-mute">{row.entity_id ?? "--"}</p>
        </div>
      ),
    },
    {
      key: "ip",
      header: "IP",
      render: (row) => <span className="num text-xs">{row.ip_address ?? "--"}</span>,
    },
    {
      key: "status",
      header: "Result",
      render: (row) => (
        <Badge tone={row.status === "success" ? "gain" : "loss"}>{row.status}</Badge>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <Card
        title="Audit trail"
        subtitle="Client actions written by the API, order events written by the database triggers"
      >
        <div className="flex flex-col gap-3 border-b border-edge/70 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            <div className="w-full sm:w-56">
              <select
                className="input"
                value={action}
                onChange={(event) => setAction(event.target.value)}
                aria-label="Filter by action"
              >
                <option value="">All actions</option>
                {ACTIONS.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
            <div className="w-full sm:w-44">
              <select
                className="input"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                aria-label="Filter by result"
              >
                <option value="">Any result</option>
                <option value="success">Success</option>
                <option value="failure">Failure</option>
              </select>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge tone="neutral">{(audit.data ?? []).length} entries</Badge>
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => {
                setAction("");
                setStatus("");
              }}
            >
              Reset
            </button>
          </div>
        </div>

        {audit.error ? (
          <div className="p-5">
            <ErrorNote message={audit.error.message} onRetry={audit.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={audit.data}
            loading={audit.loading}
            rowKey={(row) => row.audit_id}
            emptyTitle="No audit entries match"
            emptyHint="Sign in, place an order or manage an indicator to generate entries."
          />
        )}
      </Card>
    </div>
  );
}

export default function AuditLogsPage() {
  return (
    <RequireAdmin>
      <AuditContent />
    </RequireAdmin>
  );
}
