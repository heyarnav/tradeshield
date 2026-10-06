"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { money, qty as fmtQty } from "@/lib/format";
import type { Instrument, OrderListResponse, OrderSide, OrderType } from "@/lib/types";
import { useToast } from "./toast";
import { Badge, Field, Modal, Spinner } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
  onPlaced?: () => void;
  initialSymbol?: string;
  initialSide?: OrderSide;
}

const ERROR_TONE: Record<string, "critical" | "warn"> = {
  ORDER_BLOCKED: "critical",
  INSUFFICIENT_FUNDS: "warn",
  INSUFFICIENT_HOLDINGS: "warn",
  LIMIT_PRICE_REQUIRED: "warn",
  LIMIT_PRICE_NOT_ALLOWED: "warn",
  ENTITY_INACTIVE: "warn",
  VALIDATION_ERROR: "warn",
};

export function OrderTicket({ open, onClose, onPlaced, initialSymbol, initialSide }: Props) {
  const { push } = useToast();
  const instruments = useApi<Instrument[]>(open ? "/instruments" : null);

  const [symbol, setSymbol] = useState(initialSymbol ?? "ACME");
  const [side, setSide] = useState<OrderSide>(initialSide ?? "BUY");
  const [orderType, setOrderType] = useState<OrderType>("MARKET");
  const [quantity, setQuantity] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [referrerDomain, setReferrerDomain] = useState("");
  const [referrerUrl, setReferrerUrl] = useState("");
  const [simulatedIp, setSimulatedIp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState<OrderListResponse | null>(null);
  // Synchronous in-flight guard: `submitting` state is only applied on the next
  // render, so a double click (or an impatient Enter key) could fire two orders.
  const inFlight = useRef(false);

  useEffect(() => {
    if (!open) return;
    setSymbol(initialSymbol ?? "ACME");
    setSide(initialSide ?? "BUY");
    setFailure(null);
    setSuccess(null);
  }, [open, initialSymbol, initialSide]);

  const instrument = useMemo(
    () => instruments.data?.find((row) => row.symbol === symbol) ?? null,
    [instruments.data, symbol],
  );

  const parsedQty = Number(quantity);
  const parsedLimit = orderType === "LIMIT" ? Number(limitPrice) : null;
  const unitPrice = orderType === "LIMIT" ? parsedLimit : instrument?.current_price ?? 0;
  const estimate =
    Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty * (unitPrice || 0) : 0;

  const clientValid =
    Number.isFinite(parsedQty) &&
    parsedQty > 0 &&
    (orderType === "MARKET" || (Number.isFinite(parsedLimit) && (parsedLimit ?? 0) > 0));

  async function submit() {
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    setFailure(null);
    setSuccess(null);
    try {
      const body: Record<string, unknown> = {
        instrument: symbol,
        side,
        order_type: orderType,
        quantity: parsedQty,
      };
      if (orderType === "LIMIT") body.limit_price = parsedLimit;
      if (referrerDomain.trim()) body.referrer_domain = referrerDomain.trim();
      if (referrerUrl.trim()) body.referrer_url = referrerUrl.trim();

      const headers = simulatedIp.trim() ? { "X-Origin-IP": simulatedIp.trim() } : undefined;
      const data = await api<OrderListResponse>("/orders", {
        method: "POST",
        body,
        headers,
      });
      setSuccess(data);
      const executed = data.execution?.executed;
      push(
        executed ? "success" : "info",
        executed
          ? `${side} ${fmtQty(parsedQty)} ${symbol} filled at ${money(data.order.execution_price)}`
          : `${side} ${fmtQty(parsedQty)} ${symbol} queued -- limit price not met`,
      );
      if (data.order.risk_status === "FLAGGED") {
        push("info", "Order flagged by security screening and recorded for review.");
      }
      onPlaced?.();
    } catch (error) {
      const apiError =
        error instanceof ApiError ? error : new ApiError(0, "UNKNOWN", "Order failed.");
      setFailure(apiError);
      push("error", apiError.message);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Order ticket"
      subtitle="Screened against active threat indicators before it reaches the database"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="button"
            className={side === "BUY" ? "btn-primary" : "btn-danger"}
            onClick={submit}
            disabled={submitting || !clientValid || !instrument}
          >
            {submitting ? "Submitting..." : `${side} ${symbol}`}
          </button>
        </>
      }
    >
      {instruments.loading && <Spinner label="Loading instruments..." />}

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Instrument">
            <select
              className="input"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
            >
              {(instruments.data ?? []).map((row) => (
                <option key={row.instrument_id} value={row.symbol}>
                  {row.symbol} * {row.name}
                  {row.is_active ? "" : " (inactive)"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Side">
            <div className="grid grid-cols-2 gap-2">
              {(["BUY", "SELL"] as OrderSide[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setSide(option)}
                  className={`btn btn-xs ${
                    side === option
                      ? option === "BUY"
                        ? "bg-gain/15 text-gain ring-1 ring-gain/40"
                        : "bg-loss/15 text-loss ring-1 ring-loss/40"
                      : "bg-ink-850 text-mute"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Order type">
            <div className="grid grid-cols-2 gap-2">
              {(["MARKET", "LIMIT"] as OrderType[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setOrderType(option)}
                  className={`btn btn-xs ${
                    orderType === option
                      ? "bg-brand/15 text-brand-soft ring-1 ring-brand/40"
                      : "bg-ink-850 text-mute"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Quantity">
            <input
              className="input num"
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </Field>
        </div>

        {orderType === "LIMIT" && (
          <Field
            label="Limit price"
            hint={
              instrument
                ? `Market price ${money(instrument.current_price)} -- ${
                    side === "BUY"
                      ? "fills now when market ? limit"
                      : "fills now when market ? limit"
                  }`
                : undefined
            }
          >
            <input
              className="input num"
              inputMode="decimal"
              placeholder={instrument ? String(instrument.current_price) : ""}
              value={limitPrice}
              onChange={(event) => setLimitPrice(event.target.value)}
            />
          </Field>
        )}

        <div className="rounded-xl border border-edge bg-ink-850/70 px-4 py-3 text-sm">
          <div className="flex items-center justify-between text-mute">
            <span>{side === "BUY" ? "Estimated cost" : "Estimated proceeds"}</span>
            <span className="num text-text">{money(estimate)}</span>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-mute">
            <span>Market price</span>
            <span className="num">{instrument ? money(instrument.current_price) : "--"}</span>
          </div>
        </div>

        <details className="rounded-xl border border-edge bg-ink-850/40 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-mute">
            Security context (demo)
          </summary>
          <p className="mt-2 text-[11px] leading-relaxed text-mute">
            The Flask API sends the order IP to PostgreSQL, where a BEFORE INSERT trigger matches
            it against active, non-expired threat indicators. Confidence ? 80 blocks the order,
            60-79 flags it. The simulated IP below is ignored unless the API is started with
            TRUST_CLIENT_IP_HEADER=true, which is how the blocking demo is run locally.
          </p>
          <div className="mt-3 space-y-3">
            <Field
              label="Simulated source IP"
              hint="Only used when the API runs with TRUST_CLIENT_IP_HEADER=true (development)"
            >
              <input
                className="input num"
                placeholder="e.g. 198.51.100.66 (seeded C2 indicator)"
                value={simulatedIp}
                onChange={(event) => setSimulatedIp(event.target.value)}
              />
            </Field>
            <Field label="Referrer domain" hint="e.g. promo-trades.io (seeded 68% indicator)">
              <input
                className="input"
                placeholder="optional"
                value={referrerDomain}
                onChange={(event) => setReferrerDomain(event.target.value)}
              />
            </Field>
            <Field label="Referrer URL" hint="optional">
              <input
                className="input"
                placeholder="http://..."
                value={referrerUrl}
                onChange={(event) => setReferrerUrl(event.target.value)}
              />
            </Field>
          </div>
        </details>

        {failure && (
          <div
            className={`animate-fade-up rounded-xl border px-4 py-3 text-sm ${
              ERROR_TONE[failure.code] === "critical"
                ? "border-loss/40 bg-loss/10 text-loss"
                : "border-warn/40 bg-warn/10 text-warn"
            }`}
          >
            <div className="flex items-center gap-2">
              <Badge tone={ERROR_TONE[failure.code] === "critical" ? "critical" : "warn"}>
                {failure.code}
              </Badge>
              <span>{failure.message}</span>
            </div>
          </div>
        )}

        {success && (
          <div className="animate-fade-up rounded-xl border border-gain/40 bg-gain/10 px-4 py-3 text-sm text-gain">
            <p className="font-medium">
              {success.execution?.executed ? "Order executed" : "Order accepted -- pending"}
            </p>
            <p className="mt-1 text-xs text-mute">
              {success.execution?.executed
                ? `${fmtQty(success.order.quantity)} ${success.order.symbol} at ${money(
                    success.order.execution_price,
                  )} * ${success.order.status} * risk ${success.order.risk_status}`
                : (success.execution?.reason ?? "Waiting for the limit price to be satisfied.")}
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}
