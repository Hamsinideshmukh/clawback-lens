import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Clawback Lens — Dispute Resolution",
  description: "Chargeback disputes resolved with computer-vision evidence extraction and a deterministic rule engine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="bg-navy text-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Clawback <span className="text-gold">Lens</span>
            </Link>
            <p className="hidden text-sm text-slate-300 sm:block">AI proposes evidence · the rule engine decides</p>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
