"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Icon } from "@/components/icons";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, money, qty as fmtQty, signedMoney } from "@/lib/format";
import {
  AllocationBar,
  AreaChart,
  Badge,
  Card,
  DataTable,
  ErrorNote,
  RiskBadge,
  SideBadge,
  StatCard,
  StatusBadge,
  type Column,
} from "@/components/ui";
import type { AccountDetail, Holding, LedgerRow, Order } from "@/lib/types";

export default function DashboardPage() {
  const { user, isAdmin } = useAuth();
  const account = useApi<AccountDetail>("/account");
  const holdings = useApi<Holding[]>("/portfolio/holdings");
  const orders = useApi<Order[]>("/orders?limit=6");
  const ledger = useApi<LedgerRow[]>("/transactions?limit=200");

  const history = useMemo(() => (ledger.data ?? []).slice().reverse(), [ledger.data]);
  const balanceSeries = useMemo(() => history.map((row) => row.balance_after), [history]);

  const pnlTone = (account.data?.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss";
  const flagged = (orders.data ?? []).filter((order) => order.risk_status === "FLAGGED").length;

  const orderColumns: Column<Order>[] = [
    {
      key: "placed",
      header: "Placed",
      render: (row) => <span className="num text-xs">{dateTime(row.placed_at)}</span>,
    },
    { key: "symbol", header: "Instrument", render: (row) => (
      <div>
        <p className="font-medium">{row.symbol}</p>
        <p className="text-xs text-mute">{row.instrument_name}</p>
      </div>
    ) },
    { key: "side", header: "Side", render: (row) => <SideBadge side={row.side} /> },
    {
      key: "type",
      header: "Type",
      render: (row) => <span className="text-xs text-mute">{row.order_type}</span>,
    },
    {
      key: "qty",
      header: "Qty",
      align: "right",
      render: (row) => <span className="num">{fmtQty(row.quantity)}</span>,
    },
    {
      key: "price",
      header: "Fill",
      align: "right",
      render: (row) => (
        <span className="num">{row.execution_price ? money(row.execution_price) : "--"}</span>
      ),
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "risk", header: "Risk", render: (row) => <RiskBadge risk={row.risk_status} /> },
  ];

  return (
    <div className="space-y-5">
      {account.error && <ErrorNote message={account.error.message} onRetry={account.reload} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total equity"
          value={money(account.data?.total_equity)}
          sub={`Account ${account.data?.account_number ?? "--"}`}
        />
        <StatCard
          label="Cash balance"
          value={money(account.data?.cash_balance)}
          sub="Available for new orders"
          tone="brand"
        />
        <StatCard
          label="Market value"
          value={money(account.data?.market_value)}
          sub={`${account.data?.holdings_count ?? 0} open position(s)`}
        />
        <StatCard
          label="Unrealised P&L"
          value={signedMoney(account.data?.unrealized_pnl)}
          sub={`Cost basis ${money(account.data?.cost_basis)}`}
          tone={pnlTone}
        />
      </div>

      {flagged > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
          <span>
            <strong>{flagged}</strong> of your recent orders were flagged by threat screening and
            are held for review.
          </span>
          <Link href="/orders?risk=FLAGGED" className="btn-ghost btn-xs">
            Review flagged orders
          </Link>
        </div>
      )}

      {isAdmin && (
        <Link
          href="/admin/security"
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-alert/30 bg-alert/10 px-4 py-3 text-sm text-alert transition hover:bg-alert/15"
        >
          <span className="flex items-center gap-2">
            <Icon name="shield" className="h-4 w-4" />
            You have security operations access -- open the threat dashboard
          </span>
          <span className="text-xs">admin ?</span>
        </Link>
      )}

      <div className="grid gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Cash balance over time"
          subtitle="Running balance from the executed trade ledger"
        >
          {ledger.loading ? (
            <div className="px-5 pb-6">
              <div className="skeleton h-32 w-full" />
            </div>
          ) : balanceSeries.length >= 2 ? (
            <AreaChart
              values={balanceSeries}
              labels={[
                dateTime(history[0].created_at),
                dateTime(history[history.length - 1].created_at),
              ]}
            />
          ) : (
            <p className="px-5 py-10 text-center text-xs text-mute">
              Execute a trade to start tracking your cash balance.
            </p>
          )}
        </Card>

        <Card title="Holdings" subtitle="Allocation of invested capital">
          {holdings.error ? (
            <div className="p-5">
              <ErrorNote message={holdings.error.message} onRetry={holdings.reload} />
            </div>
          ) : (
            <div className="space-y-4 p-5">
              {(holdings.data ?? []).length === 0 && !holdings.loading && (
                <p className="py-6 text-center text-xs text-mute">No positions yet.</p>
              )}
              {(holdings.data ?? []).map((holding) => (
                <div key={holding.holding_id}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="font-medium">{holding.symbol}</span>
                    <span className="num text-mute">{money(holding.market_value)}</span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-mute">
                    {fmtQty(holding.quantity)} @ {money(holding.avg_buy_price)}
                  </p>
                  <div className="mt-2">
                    <AllocationBar
                      value={holding.market_value}
                      total={account.data?.market_value ?? 0}
                      tone={holding.unrealized_pnl >= 0 ? "#22c98a" : "#ff5d6c"}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card
        title="Recent orders"
        subtitle="Latest activity across your account"
        action={
          <Link href="/orders" className="btn-ghost btn-xs">
            View all
          </Link>
        }
      >
        <DataTable
          columns={orderColumns}
          rows={orders.data}
          loading={orders.loading}
          rowKey={(row) => row.order_id}
          emptyTitle="No orders yet"
          emptyHint="Place your first order from the Market or Orders page."
        />
      </Card>

      <p className="pb-4 text-xs text-mute">
        Signed in as <span className="text-text">{user?.email}</span> *{" "}
        <Badge tone={isAdmin ? "alert" : "brand"}>{user?.role}</Badge>
      </p>
    </div>
  );
}
