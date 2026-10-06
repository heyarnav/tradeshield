"use client";

import { useState } from "react";
import { OrderTicket } from "@/components/order-ticket";
import {
  AllocationBar,
  Badge,
  Card,
  DataTable,
  ErrorNote,
  StatCard,
  type Column,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateOnly, money, pct, qty as fmtQty, signedMoney } from "@/lib/format";
import type { Holding, PortfolioSummary } from "@/lib/types";

export default function PortfolioPage() {
  const [ticketOpen, setTicketOpen] = useState(false);
  const summary = useApi<PortfolioSummary>("/portfolio");
  const holdings = useApi<Holding[]>("/portfolio/holdings");

  const marketValue = summary.data?.market_value ?? 0;
  const pnl = summary.data?.unrealized_pnl ?? 0;
  const costBasis = summary.data?.cost_basis ?? 0;
  const pnlPercent = costBasis > 0 ? (pnl / costBasis) * 100 : 0;

  const columns: Column<Holding>[] = [
    {
      key: "symbol",
      header: "Position",
      render: (row) => (
        <div>
          <p className="font-semibold">{row.symbol}</p>
          <p className="text-xs text-mute">{row.name}</p>
        </div>
      ),
    },
    {
      key: "quantity",
      header: "Quantity",
      align: "right",
      render: (row) => <span className="num">{fmtQty(row.quantity)}</span>,
    },
    {
      key: "avg",
      header: "Avg cost",
      align: "right",
      render: (row) => <span className="num">{money(row.avg_buy_price, 4)}</span>,
    },
    {
      key: "last",
      header: "Last",
      align: "right",
      render: (row) => <span className="num">{money(row.current_price, 4)}</span>,
    },
    {
      key: "value",
      header: "Market value",
      align: "right",
      render: (row) => <span className="num">{money(row.market_value)}</span>,
    },
    {
      key: "pnl",
      header: "Unrealised P&L",
      align: "right",
      render: (row) => (
        <div>
          <p className={`num ${row.unrealized_pnl >= 0 ? "text-gain" : "text-loss"}`}>
            {signedMoney(row.unrealized_pnl)}
          </p>
          <p className={`num text-[11px] ${row.unrealized_pnl >= 0 ? "text-gain" : "text-loss"}`}>
            {pct(
              row.cost_basis > 0 ? (row.unrealized_pnl / row.cost_basis) * 100 : 0,
            )}
          </p>
        </div>
      ),
    },
    {
      key: "weight",
      header: "Weight",
      render: (row) => (
        <div className="w-28">
          <AllocationBar
            value={row.market_value}
            total={marketValue}
            tone={row.unrealized_pnl >= 0 ? "#22c98a" : "#ff5d6c"}
          />
          <p className="mt-1 text-[11px] text-mute">
            {marketValue > 0 ? pct((row.market_value / marketValue) * 100, 1) : "0.0%"}
          </p>
        </div>
      ),
    },
    {
      key: "opened",
      header: "Opened",
      align: "right",
      render: (row) => <span className="text-xs text-mute">{dateOnly(row.opened_at)}</span>,
    },
  ];

  return (
    <div className="space-y-5">
      {summary.error && (
        <ErrorNote message={summary.error.message} onRetry={summary.reload} />
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total equity"
          value={money(summary.data?.total_equity)}
          sub="Cash + market value"
        />
        <StatCard
          label="Cash"
          value={money(summary.data?.cash_balance)}
          tone="brand"
          sub={`Status ${summary.data?.account_status ?? "--"}`}
        />
        <StatCard label="Market value" value={money(marketValue)} sub="Marked to last price" />
        <StatCard
          label="Unrealised P&L"
          value={signedMoney(pnl)}
          sub={costBasis > 0 ? `${pct(pnlPercent)} on cost` : "No cost basis"}
          tone={pnl >= 0 ? "gain" : "loss"}
        />
      </div>

      <Card
        title="Holdings"
        subtitle="Weighted-average cost basis maintained by the database on every BUY"
        action={
          <button type="button" className="btn-primary btn-xs" onClick={() => setTicketOpen(true)}>
            Trade
          </button>
        }
      >
        {holdings.error ? (
          <div className="p-5">
            <ErrorNote message={holdings.error.message} onRetry={holdings.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={holdings.data}
            loading={holdings.loading}
            rowKey={(row) => row.holding_id}
            emptyTitle="No open positions"
            emptyHint="Buy an instrument to start building your portfolio."
          />
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-2 text-xs text-mute">
        <Badge tone="neutral">Average cost basis: {money(costBasis)}</Badge>
        <Badge tone="neutral">Positions: {summary.data?.holdings_count ?? 0}</Badge>
        <Badge tone="neutral">Account: {summary.data?.account_number ?? "--"}</Badge>
      </div>

      <OrderTicket
        open={ticketOpen}
        onClose={() => setTicketOpen(false)}
        onPlaced={() => {
          summary.reload();
          holdings.reload();
        }}
      />
    </div>
  );
}
