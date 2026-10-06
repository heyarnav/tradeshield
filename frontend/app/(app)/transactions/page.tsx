"use client";

import { useMemo, useState } from "react";
import {
  Badge,
  Card,
  DataTable,
  ErrorNote,
  SideBadge,
  StatCard,
  type Column,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateTime, money, qty as fmtQty, signedMoney } from "@/lib/format";
import type { LedgerRow } from "@/lib/types";

export default function TransactionsPage() {
  const [side, setSide] = useState("");
  const [symbol, setSymbol] = useState("");

  const ledger = useApi<LedgerRow[]>("/transactions?limit=200");

  const filtered = useMemo(() => {
    return (ledger.data ?? []).filter((row) => {
      if (side && row.side !== side) return false;
      if (symbol && row.symbol !== symbol) return false;
      return true;
    });
  }, [ledger.data, side, symbol]);

  const totals = useMemo(() => {
    const buys = filtered.filter((row) => row.side === "BUY");
    const sells = filtered.filter((row) => row.side === "SELL");
    const sum = (rows: LedgerRow[]) =>
      rows.reduce((acc, row) => acc + Math.abs(row.cash_delta), 0);
    const net = filtered.reduce((acc, row) => acc + row.cash_delta, 0);
    return { buys: sum(buys), sells: sum(sells), net };
  }, [filtered]);

  const symbols = useMemo(
    () => Array.from(new Set((ledger.data ?? []).map((row) => row.symbol))).sort(),
    [ledger.data],
  );

  const columns: Column<LedgerRow>[] = [
    {
      key: "created",
      header: "When",
      render: (row) => <span className="num text-xs">{dateTime(row.created_at)}</span>,
    },
    {
      key: "symbol",
      header: "Instrument",
      render: (row) => (
        <div>
          <p className="font-semibold">{row.symbol}</p>
          <p className="text-xs text-mute">{row.order_type}</p>
        </div>
      ),
    },
    { key: "side", header: "Side", render: (row) => <SideBadge side={row.side} /> },
    {
      key: "quantity",
      header: "Qty",
      align: "right",
      render: (row) => <span className="num">{fmtQty(row.quantity)}</span>,
    },
    {
      key: "price",
      header: "Price",
      align: "right",
      render: (row) => <span className="num">{money(row.price, 4)}</span>,
    },
    {
      key: "delta",
      header: "Cash ?",
      align: "right",
      render: (row) => (
        <span className={`num ${row.cash_delta >= 0 ? "text-gain" : "text-loss"}`}>
          {signedMoney(row.cash_delta)}
        </span>
      ),
    },
    {
      key: "balance",
      header: "Balance after",
      align: "right",
      render: (row) => <span className="num">{money(row.balance_after)}</span>,
    },
    {
      key: "order",
      header: "Order",
      render: (row) => <span className="num text-[11px] text-mute">{row.order_id}</span>,
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Deployed on buys" value={money(totals.buys)} tone="loss" />
        <StatCard label="Realised on sells" value={money(totals.sells)} tone="gain" />
        <StatCard
          label="Net cash impact"
          value={signedMoney(totals.net)}
          tone={totals.net >= 0 ? "gain" : "loss"}
          sub="Across the current filter"
        />
      </div>

      <Card
        title="Cash ledger"
        subtitle="One row per executed trade -- written by the database inside the order transaction"
      >
        <div className="flex flex-col gap-3 border-b border-edge/70 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSide("")}
              className={`btn btn-xs ${side === "" ? "bg-brand/15 text-brand-soft ring-1 ring-brand/40" : "bg-ink-850 text-mute"}`}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setSide("BUY")}
              className={`btn btn-xs ${side === "BUY" ? "bg-gain/15 text-gain ring-1 ring-gain/40" : "bg-ink-850 text-mute"}`}
            >
              Buys
            </button>
            <button
              type="button"
              onClick={() => setSide("SELL")}
              className={`btn btn-xs ${side === "SELL" ? "bg-loss/15 text-loss ring-1 ring-loss/40" : "bg-ink-850 text-mute"}`}
            >
              Sells
            </button>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="input md:max-w-40"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              aria-label="Filter by instrument"
            >
              <option value="">All instruments</option>
              {symbols.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <Badge tone="neutral">{filtered.length} entries</Badge>
          </div>
        </div>

        {ledger.error ? (
          <div className="p-5">
            <ErrorNote message={ledger.error.message} onRetry={ledger.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={filtered}
            loading={ledger.loading}
            rowKey={(row) => row.transaction_id}
            emptyTitle="No transactions yet"
            emptyHint="Executed trades appear here with their cash impact."
          />
        )}
      </Card>
    </div>
  );
}
