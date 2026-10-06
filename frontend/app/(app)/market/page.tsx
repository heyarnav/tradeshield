"use client";

import { useMemo, useState } from "react";
import { OrderTicket } from "@/components/order-ticket";
import { Badge, Card, DataTable, ErrorNote, Modal, Spinner, type Column } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";
import type { Instrument, OrderSide } from "@/lib/types";

const ASSET_FILTERS = [
  { value: "", label: "All" },
  { value: "equity", label: "Equities" },
  { value: "etf", label: "ETFs" },
  { value: "crypto", label: "Crypto" },
  { value: "index", label: "Index" },
];

export default function MarketPage() {
  const [assetType, setAssetType] = useState("");
  const [search, setSearch] = useState("");
  const [ticket, setTicket] = useState<{ open: boolean; symbol?: string; side?: OrderSide }>({
    open: false,
  });
  const [detail, setDetail] = useState<Instrument | null>(null);

  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (assetType) params.set("asset_type", assetType);
    if (search.trim()) params.set("q", search.trim());
    const query = params.toString();
    return `/instruments${query ? `?${query}` : ""}`;
  }, [assetType, search]);

  const instruments = useApi<Instrument[]>(path);

  const columns: Column<Instrument>[] = [
    {
      key: "symbol",
      header: "Symbol",
      render: (row) => (
        <div>
          <p className="font-semibold">{row.symbol}</p>
          <p className="text-xs text-mute">{row.name}</p>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (row) => <Badge tone="brand">{row.asset_type}</Badge>,
    },
    {
      key: "exchange",
      header: "Venue",
      render: (row) => <span className="text-xs text-mute">{row.exchange}</span>,
    },
    {
      key: "price",
      header: "Last price",
      align: "right",
      render: (row) => <span className="num text-sm">{money(row.current_price, 4)}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) =>
        row.is_active ? (
          <Badge tone="gain">Trading</Badge>
        ) : (
          <Badge tone="loss">Halted</Badge>
        ),
    },
    {
      key: "actions",
      header: "Trade",
      align: "right",
      render: (row) =>
        row.is_active ? (
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={(event) => {
                event.stopPropagation();
                setTicket({ open: true, symbol: row.symbol, side: "BUY" });
              }}
            >
              Buy
            </button>
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={(event) => {
                event.stopPropagation();
                setTicket({ open: true, symbol: row.symbol, side: "SELL" });
              }}
            >
              Sell
            </button>
          </div>
        ) : (
          <span className="text-xs text-mute">--</span>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <Card
        title="Simulated market"
        subtitle="Quotes come straight from the instruments table -- every order is validated against them"
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
          <div className="flex flex-wrap gap-2">
            {ASSET_FILTERS.map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                onClick={() => setAssetType(filter.value)}
                className={`btn btn-xs ${
                  assetType === filter.value
                    ? "bg-brand/15 text-brand-soft ring-1 ring-brand/40"
                    : "bg-ink-850 text-mute"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            className="input md:max-w-xs"
            placeholder="Search symbol or name..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        {instruments.error ? (
          <div className="p-5">
            <ErrorNote message={instruments.error.message} onRetry={instruments.reload} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={instruments.data}
            loading={instruments.loading}
            rowKey={(row) => row.instrument_id}
            emptyTitle="No instruments match"
            emptyHint="Try a different asset class or search term."
          />
        )}
      </Card>

      <OrderTicket
        open={ticket.open}
        initialSymbol={ticket.symbol}
        initialSide={ticket.side}
        onClose={() => setTicket({ open: false })}
        onPlaced={instruments.reload}
      />

      <Modal
        open={detail !== null}
        title={detail ? `${detail.symbol} * ${detail.name}` : ""}
        subtitle={detail ? `${detail.asset_type} on ${detail.exchange}` : ""}
        onClose={() => setDetail(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setDetail(null)}>
              Close
            </button>
            {detail?.is_active && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  setTicket({ open: true, symbol: detail.symbol, side: "BUY" });
                  setDetail(null);
                }}
              >
                Trade {detail.symbol}
              </button>
            )}
          </>
        }
      >
        {detail && (
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="label">Last price</dt>
              <dd className="num">{money(detail.current_price, 4)}</dd>
            </div>
            <div>
              <dt className="label">Tick size</dt>
              <dd className="num">{money(detail.tick_size, 4)}</dd>
            </div>
            <div>
              <dt className="label">Instrument ID</dt>
              <dd className="num text-xs text-mute">{detail.instrument_id}</dd>
            </div>
            <div>
              <dt className="label">Price updated</dt>
              <dd className="num text-xs text-mute">{dateTime(detail.price_updated_at)}</dd>
            </div>
          </dl>
        )}
      </Modal>

      {instruments.loading && !instruments.data && <Spinner />}
    </div>
  );
}
