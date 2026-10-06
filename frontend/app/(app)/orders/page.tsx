"use client";

import { useEffect, useMemo, useState } from "react";
import { OrderTicket } from "@/components/order-ticket";
import {
  Badge,
  Card,
  DataTable,
  ErrorNote,
  Modal,
  RiskBadge,
  SideBadge,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, money, qty as fmtQty, signedMoney } from "@/lib/format";
import type { Order, OrderSide } from "@/lib/types";

interface OrderDetailResponse {
  order: Order;
  transactions: {
    transaction_id: string;
    cash_delta: number;
    balance_after: number;
    created_at: string;
    quantity: number;
    price: number;
    gross_amount: number;
  }[];
}

export default function OrdersPage() {
  const [ticket, setTicket] = useState<{ open: boolean; symbol?: string; side?: OrderSide }>({
    open: false,
  });
  const [status, setStatus] = useState("");
  const [risk, setRisk] = useState("");
  const [detail, setDetail] = useState<OrderDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // honour /orders?risk=FLAGGED deep links from the dashboard
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initial = params.get("risk");
    if (initial) setRisk(initial);
  }, []);

  const path = useMemo(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    if (risk) params.set("risk_status", risk);
    return `/orders?${params.toString()}`;
  }, [status, risk]);

  const orders = useApi<Order[]>(path);

  async function openDetail(orderId: string) {
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await api<OrderDetailResponse>(`/orders/${orderId}`));
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  const columns: Column<Order>[] = [
    {
      key: "placed",
      header: "Placed",
      render: (row) => <span className="num text-xs">{dateTime(row.placed_at)}</span>,
    },
    {
      key: "instrument",
      header: "Instrument",
      render: (row) => (
        <div>
          <p className="font-semibold">{row.symbol}</p>
          <p className="text-xs text-mute">{row.instrument_name}</p>
        </div>
      ),
    },
    { key: "side", header: "Side", render: (row) => <SideBadge side={row.side} /> },
    {
      key: "type",
      header: "Type",
      render: (row) => <span className="text-xs text-mute">{row.order_type}</span>,
    },
    {
      key: "quantity",
      header: "Qty",
      align: "right",
      render: (row) => <span className="num">{fmtQty(row.quantity)}</span>,
    },
    {
      key: "limit",
      header: "Limit",
      align: "right",
      render: (row) => (
        <span className="num">{row.limit_price ? money(row.limit_price) : "--"}</span>
      ),
    },
    {
      key: "fill",
      header: "Fill price",
      align: "right",
      render: (row) => (
        <span className="num">{row.execution_price ? money(row.execution_price) : "--"}</span>
      ),
    },
    {
      key: "gross",
      header: "Gross",
      align: "right",
      render: (row) => <span className="num">{row.gross_amount ? money(row.gross_amount) : "--"}</span>,
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "risk",
      header: "Screening",
      render: (row) =>
        row.risk_status === "FLAGGED" ? (
          <span title={row.security_note ?? undefined}>
            <RiskBadge risk={row.risk_status} />
          </span>
        ) : (
          <RiskBadge risk={row.risk_status} />
        ),
    },
  ];

  const pending = (orders.data ?? []).filter((row) => row.status === "PENDING").length;
  const flagged = (orders.data ?? []).filter((row) => row.risk_status === "FLAGGED").length;

  return (
    <div className="space-y-5">
      <Card
        title="Order blotter"
        subtitle="Orders blocked by security screening never reach this list -- see the admin console"
        action={
          <button
            type="button"
            className="btn-primary btn-xs"
            onClick={() => setTicket({ open: true })}
          >
            Place order
          </button>
        }
      >
        <div className="flex flex-col gap-3 border-b border-edge/70 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-full sm:w-48">
              <select
                className="input"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                aria-label="Filter by status"
              >
                <option value="">All statuses</option>
                <option value="EXECUTED">Executed</option>
                <option value="PENDING">Pending</option>
                <option value="CANCELLED">Cancelled</option>
                <option value="REJECTED">Rejected</option>
              </select>
            </div>
            <div className="w-full sm:w-48">
              <select
                className="input"
                value={risk}
                onChange={(event) => setRisk(event.target.value)}
                aria-label="Filter by screening"
              >
                <option value="">All screenings</option>
                <option value="CLEAR">Clear</option>
                <option value="FLAGGED">Flagged</option>
              </select>
            </div>
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => {
                setStatus("");
                setRisk("");
              }}
            >
              Reset
            </button>
          </div>
          <div className="flex gap-2 text-xs">
            <Badge tone="warn">{pending} pending</Badge>
            <Badge tone={flagged ? "alert" : "neutral"}>{flagged} flagged</Badge>
          </div>
        </div>

        {orders.error ? (
          <div className="p-5">
            <ErrorNote message={orders.error.message} onRetry={orders.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={orders.data}
            loading={orders.loading}
            rowKey={(row) => row.order_id}
            onRowClick={(row) => openDetail(row.order_id)}
            emptyTitle="No orders match"
            emptyHint="Adjust the filters or place a new order."
          />
        )}
      </Card>

      <Card title="How orders are handled" subtitle="Database-enforced, synchronous, auditable">
        <ul className="space-y-3 text-sm text-mute">
          <li className="flex gap-3">
            <Badge tone="brand">1</Badge>
            <span>
              A <code className="text-brand-soft">BEFORE INSERT</code> trigger screens the order
              context against active, non-expired indicators. Confidence ? 80 raises an exception --
              the order row is never created.
            </span>
          </li>
          <li className="flex gap-3">
            <Badge tone="brand">2</Badge>
            <span>
              A second trigger validates the account, instrument, quantity, price rule, funds and
              holdings before the row is accepted.
            </span>
          </li>
          <li className="flex gap-3">
            <Badge tone="brand">3</Badge>
            <span>
              Market orders (and satisfied limit orders) execute through{" "}
              <code className="text-brand-soft">fn_execute_order()</code> inside the same
              transaction: row locks, weighted-average cost, execution and ledger rows.
            </span>
          </li>
          <li className="flex gap-3">
            <Badge tone="brand">4</Badge>
            <span>
              Blocked attempts are re-recorded by the API in a separate transaction, so the security
              event and audit entry survive the rollback.
            </span>
          </li>
        </ul>
      </Card>

      <OrderTicket
        open={ticket.open}
        initialSymbol={ticket.symbol}
        initialSide={ticket.side}
        onClose={() => setTicket({ open: false })}
        onPlaced={orders.reload}
      />

      <Modal
        open={detail !== null || detailLoading}
        title="Order detail"
        subtitle={detail ? `${detail.order.symbol} * ${detail.order.side} ${detail.order.order_type}` : "Loading..."}
        onClose={() => setDetail(null)}
        width="max-w-2xl"
      >
        {detail && (
          <div className="space-y-5">
            <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="label">Status</dt>
                <dd>
                  <StatusBadge status={detail.order.status} />
                </dd>
              </div>
              <div>
                <dt className="label">Screening</dt>
                <dd>
                  <RiskBadge risk={detail.order.risk_status} />
                </dd>
              </div>
              <div>
                <dt className="label">Quantity</dt>
                <dd className="num">{fmtQty(detail.order.quantity)}</dd>
              </div>
              <div>
                <dt className="label">Limit price</dt>
                <dd className="num">
                  {detail.order.limit_price ? money(detail.order.limit_price) : "--"}
                </dd>
              </div>
              <div>
                <dt className="label">Fill price</dt>
                <dd className="num">
                  {detail.order.execution_price ? money(detail.order.execution_price) : "--"}
                </dd>
              </div>
              <div>
                <dt className="label">Origin IP</dt>
                <dd className="num text-xs">{detail.order.origin_ip}</dd>
              </div>
              <div>
                <dt className="label">Placed</dt>
                <dd className="num text-xs">{dateTime(detail.order.placed_at)}</dd>
              </div>
              <div>
                <dt className="label">Order ID</dt>
                <dd className="num text-[11px] text-mute">{detail.order.order_id}</dd>
              </div>
              {detail.order.security_note && (
                <div className="col-span-2 sm:col-span-3">
                  <dt className="label">Security note</dt>
                  <dd className="text-warn">{detail.order.security_note}</dd>
                </div>
              )}
            </dl>

            <div>
              <p className="section-title mb-2">Cash ledger entries</p>
              {detail.transactions.length === 0 ? (
                <p className="text-xs text-mute">No cash movement yet.</p>
              ) : (
                <ul className="space-y-2">
                  {detail.transactions.map((row) => (
                    <li
                      key={row.transaction_id}
                      className="flex items-center justify-between rounded-xl border border-edge bg-ink-850/60 px-3 py-2 text-sm"
                    >
                      <span className="num text-xs text-mute">
                        {dateTime(row.created_at)} * {fmtQty(row.quantity)} @ {money(row.price)}
                      </span>
                      <span
                        className={`num ${row.cash_delta >= 0 ? "text-gain" : "text-loss"}`}
                      >
                        {signedMoney(row.cash_delta)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
