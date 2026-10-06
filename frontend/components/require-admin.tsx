"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { Badge, Card } from "./ui";
import { Icon } from "./icons";

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { ready, user, isAdmin } = useAuth();

  if (!ready || !user) {
    return (
      <div className="flex items-center gap-3 py-24 text-sm text-mute">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
        Checking access...
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <Card title="Administrator access required">
        <div className="flex items-start gap-3 text-sm text-mute">
          <Icon name="shield" className="mt-0.5 h-5 w-5 text-warn" />
          <div>
            <p>
              The security console is restricted to users with the{" "}
              <Badge tone="alert">admin</Badge> role. You are signed in as{" "}
              <Badge tone="brand">{user.role}</Badge>.
            </p>
            <p className="mt-2">
              The Flask API returns <code className="text-warn">403 FORBIDDEN</code> for these
              routes regardless of what the browser requests.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  return <>{children}</>;
}
