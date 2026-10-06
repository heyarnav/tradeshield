import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/toast";

export const metadata: Metadata = {
  title: "TradeShield -- Trading with threat intelligence",
  description:
    "Simulated trading platform with database-enforced threat screening, blocked-order auditing and a live security operations console.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
