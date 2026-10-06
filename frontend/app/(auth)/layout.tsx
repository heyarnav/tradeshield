import { Icon } from "@/components/icons";

const HIGHLIGHTS = [
  {
    title: "Orders screened in the database",
    body: "A BEFORE INSERT trigger matches every order's context against active threat indicators -- the order row is never written when the threat is critical.",
  },
  {
    title: "Blocked orders stay on record",
    body: "The rejected order rolls back, then the security event and audit trail are committed in a separate transaction -- evidence survives the block.",
  },
  {
    title: "One synchronous trading core",
    body: "Market and limit orders execute inside a single PostgreSQL transaction with row locks, weighted-average cost and an append-only cash ledger.",
  },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden border-r border-edge p-10 lg:flex lg:flex-col lg:justify-between">
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand/20 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white shadow-glow">
            <Icon name="shield" className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight">TradeShield</p>
            <p className="text-[10px] uppercase tracking-[0.2em] text-mute">
              Trading * Intelligence
            </p>
          </div>
        </div>

        <div className="relative max-w-md space-y-8">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Trade with a security layer that cannot be bypassed.
          </h1>
          <ul className="space-y-5">
            {HIGHLIGHTS.map((item) => (
              <li key={item.title} className="flex gap-3">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                <div>
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-mute">{item.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-mute">
          Simulated market data * educational project * no real money
        </p>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">{children}</main>
    </div>
  );
}
