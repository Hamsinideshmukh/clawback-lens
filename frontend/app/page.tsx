"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { NewCaseForm } from "@/components/NewCaseForm";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { money, timeLeft } from "@/lib/format";
import type { CaseList, CaseStatus } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

const FILTERS: (CaseStatus | undefined)[] = [undefined, "open", "escalated", "resolved"];
const never = () => false;

export default function Dashboard() {
  const [filter, setFilter] = useState<CaseStatus | undefined>();
  const { data, error, refresh } = usePolling<CaseList>(() => api.listCases(filter), never);
  useEffect(() => void refresh(), [filter, refresh]);
  const counts = data?.status_counts ?? {};

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {(["open", "escalated", "resolved"] as const).map((status) => (
            <div key={status} className="card">
              <p className="text-sm capitalize text-slate-500">{status === "escalated" ? "Needs review" : status}</p>
              <p className="mt-1 text-3xl font-semibold text-navy">{counts[status] ?? 0}</p>
            </div>
          ))}
        </div>

        <div className="card overflow-x-auto p-0">
          <div className="flex gap-2 border-b border-slate-200 p-4">
            {FILTERS.map((f) => (
              <button
                key={f ?? "all"}
                onClick={() => setFilter(f)}
                className={`btn ${filter === f ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {f ?? "All"}
              </button>
            ))}
          </div>
          {error && <p className="p-4 text-sm text-red">Backend unreachable: {error}</p>}
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Merchant</th>
                <th className="px-4 py-3">Reason code</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Response window</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/cases/${c.id}`} className="font-medium text-blue hover:underline">
                      {c.merchant_name}
                    </Link>
                    <p className="text-xs text-slate-400">{c.transaction_id}</p>
                  </td>
                  <td className="px-4 py-3">RC {c.reason_code}</td>
                  <td className="px-4 py-3">{money(c.amount, c.currency)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} outcome={c.outcome} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">{c.status === "open" ? timeLeft(c.respond_by) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data?.items.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No cases yet.</p>}
        </div>
      </section>

      <aside>
        <NewCaseForm />
      </aside>
    </div>
  );
}
