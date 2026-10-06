"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Icon, type IconName } from "./icons";
import { Badge } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  hint: string;
}

const TRADING_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard", hint: "Overview" },
  { href: "/market", label: "Market", icon: "chart", hint: "Instruments & quotes" },
  { href: "/portfolio", label: "Portfolio", icon: "briefcase", hint: "Holdings & valuation" },
  { href: "/orders", label: "Orders", icon: "orders", hint: "Blotter & tickets" },
  { href: "/transactions", label: "Transactions", icon: "ledger", hint: "Cash ledger" },
  { href: "/account", label: "Account", icon: "user", hint: "Profile & balance" },
];

const SECURITY_NAV: NavItem[] = [
  { href: "/admin/security", label: "Security", icon: "shield", hint: "Threat dashboard" },
  { href: "/admin/threats", label: "Indicators", icon: "search", hint: "Threat intelligence" },
  { href: "/admin/blocked", label: "Blocked", icon: "blocked", hint: "Blocked & flagged" },
  { href: "/admin/audit", label: "Audit", icon: "audit", hint: "Audit trail" },
];

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Portfolio at a glance" },
  "/market": { title: "Market", subtitle: "Simulated instruments and live quotes" },
  "/portfolio": { title: "Portfolio", subtitle: "Holdings, valuation and P&L" },
  "/orders": { title: "Orders", subtitle: "Order blotter and ticket" },
  "/transactions": { title: "Transactions", subtitle: "Executed trades and cash movements" },
  "/account": { title: "Account", subtitle: "Profile, balance and access" },
  "/admin/security": { title: "Security Dashboard", subtitle: "Threat posture and events" },
  "/admin/threats": { title: "Threat Indicators", subtitle: "IP, domain, URL and hash intelligence" },
  "/admin/blocked": { title: "Blocked Orders", subtitle: "Rejected and screened order attempts" },
  "/admin/audit": { title: "Audit Logs", subtitle: "Who did what, when and from where" },
};

function Brand() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white shadow-glow">
        <Icon name="shield" className="h-5 w-5" />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-tight">TradeShield</span>
        <span className="block text-[10px] uppercase tracking-[0.18em] text-mute">
          Trading * Intelligence
        </span>
      </span>
    </Link>
  );
}

function NavGroup({
  title,
  items,
  pathname,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
  onNavigate: () => void;
}) {
  return (
    <div className="mt-6">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-mute/70">
        {title}
      </p>
      <nav className="space-y-1">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={`nav-link ${active ? "nav-link-active" : ""}`}
            >
              <Icon name={item.icon} className="h-[18px] w-[18px]" />
              <span className="flex-1">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, ready, isAdmin, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [apiUp, setApiUp] = useState<boolean | null>(null);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        await api<{ status: string }>("/health");
        if (active) setApiUp(true);
      } catch {
        if (active) setApiUp(false);
      }
    };
    check();
    const timer = window.setInterval(check, 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-mute">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
          Loading TradeShield>>
        </div>
      </div>
    );
  }

  const meta = PAGE_META[pathname] ?? { title: "TradeShield", subtitle: "" };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 flex items-center gap-3 border-b border-edge bg-ink-950/90 px-4 py-3 backdrop-blur lg:hidden">
        <button
          type="button"
          className="rounded-lg p-2 text-mute transition hover:bg-ink-800 hover:text-text"
          onClick={() => setNavOpen((open) => !open)}
          aria-label="Toggle navigation"
        >
          <Icon name="menu" />
        </button>
        <Brand />
        <div className="ml-auto flex items-center gap-2">
          <Badge tone={apiUp === false ? "loss" : "gain"}>
            {apiUp === false ? "API offline" : "API live"}
          </Badge>
        </div>
      </header>

      {navOpen && (
        <div
          className="fixed inset-0 z-20 bg-ink-950/70 backdrop-blur-sm lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}

      <div className="mx-auto flex w-full max-w-[1440px]">
        <aside
          className={`${
            navOpen ? "block" : "hidden"
          } fixed inset-y-0 left-0 z-30 w-64 overflow-y-auto border-r border-edge bg-ink-900/95 px-4 py-5 backdrop-blur lg:sticky lg:top-0 lg:block lg:h-screen lg:shrink-0 lg:bg-ink-900/50`}
        >
          <div className="hidden lg:block">
            <Brand />
          </div>

          <NavGroup
            title="Trading"
            items={TRADING_NAV}
            pathname={pathname}
            onNavigate={() => setNavOpen(false)}
          />

          {isAdmin && (
            <NavGroup
              title="Security operations"
              items={SECURITY_NAV}
              pathname={pathname}
              onNavigate={() => setNavOpen(false)}
            />
          )}

          <div className="mt-8 border-t border-edge/70 pt-4">
            <div className="flex items-center gap-3 px-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink-800 text-sm font-semibold text-brand-soft">
                {user.full_name.slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{user.full_name}</p>
                <p className="truncate text-[11px] text-mute">{user.email}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between px-2">
              <Badge tone={isAdmin ? "alert" : "brand"}>{user.role}</Badge>
              <button
                type="button"
                onClick={logout}
                className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-mute transition hover:bg-ink-800 hover:text-loss"
              >
                <Icon name="logout" className="h-4 w-4" />
                Sign out
              </button>
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{meta.title}</h1>
              {meta.subtitle && <p className="text-sm text-mute">{meta.subtitle}</p>}
            </div>
            <div className="hidden items-center gap-2 lg:flex">
              <Badge tone={apiUp === false ? "loss" : "gain"}>
                {apiUp === false ? "API offline" : "API live"}
              </Badge>
            </div>
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
