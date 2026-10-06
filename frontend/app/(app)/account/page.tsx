"use client";

import { Badge, Card, ErrorNote, StatCard } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, money } from "@/lib/format";
import type { AccountDetail } from "@/lib/types";

export default function AccountPage() {
  const { user, account, logout, isAdmin } = useAuth();
  const detail = useApi<AccountDetail>("/account");

  return (
    <div className="space-y-5">
      {detail.error && <ErrorNote message={detail.error.message} onRetry={detail.reload} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Cash balance" value={money(detail.data?.cash_balance)} tone="brand" />
        <StatCard label="Market value" value={money(detail.data?.market_value)} />
        <StatCard label="Total equity" value={money(detail.data?.total_equity)} />
        <StatCard
          label="Account status"
          value={detail.data?.account_status ?? "--"}
          tone={detail.data?.account_status === "active" ? "gain" : "loss"}
          sub={detail.data?.currency ?? "USD"}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Profile">
          <dl className="space-y-4 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Full name</dt>
              <dd className="font-medium">{user?.full_name}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Email</dt>
              <dd className="num text-xs">{user?.email}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Role</dt>
              <dd>
                <Badge tone={isAdmin ? "alert" : "brand"}>{user?.role}</Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">User ID</dt>
              <dd className="num text-[11px] text-mute">{user?.user_id}</dd>
            </div>
          </dl>
        </Card>

        <Card title="Trading account">
          <dl className="space-y-4 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Account number</dt>
              <dd className="num">{detail.data?.account_number ?? "--"}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Currency</dt>
              <dd className="num">{detail.data?.currency ?? "USD"}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Opened</dt>
              <dd className="num text-xs">{dateTime(detail.data?.created_at)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">Account ID</dt>
              <dd className="num text-[11px] text-mute">{detail.data?.account_id}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-mute">API account record</dt>
              <dd className="num text-[11px] text-mute">{account?.account_number ?? "--"}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card
        title="Access & security"
        subtitle="How this session is authorised"
        action={
          <button type="button" className="btn-ghost btn-xs" onClick={logout}>
            Sign out
          </button>
        }
      >
        <div className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-xl border border-edge bg-ink-850/50 p-4">
            <p className="section-title">Authentication</p>
            <p className="mt-2 text-mute">
              Password verified with Argon2, exchanged for an HS256 JWT stored in this browser.
            </p>
          </div>
          <div className="rounded-xl border border-edge bg-ink-850/50 p-4">
            <p className="section-title">Authorization</p>
            <p className="mt-2 text-mute">
              Every request re-reads your role from PostgreSQL, and all account-scoped queries are
              filtered by the account id derived from your token.
            </p>
          </div>
          <div className="rounded-xl border border-edge bg-ink-850/50 p-4">
            <p className="section-title">Order screening</p>
            <p className="mt-2 text-mute">
              Orders are screened by a database trigger. Critical matches are rejected before the
              order row exists and recorded as security events.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
