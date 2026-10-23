"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { ReasonCode } from "@/lib/types";

export function NewCaseForm() {
  const router = useRouter();
  const [codes, setCodes] = useState<ReasonCode[]>([]);
  const [form, setForm] = useState({ transaction_id: "", merchant_name: "", amount: "", reason_code: "4554" });
  const [transactionType, setTransactionType] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.reasonCodes().then(setCodes).catch(() => setError("Could not load reason codes"));
  }, []);

  const selected = codes.find((c) => c.reason_code === form.reason_code);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createCase({ ...form, transaction_type: transactionType || null });
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create case");
      setBusy(false);
    }
  }

  const field = (name: keyof typeof form) => ({
    value: form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [name]: e.target.value }),
  });

  return (
    <form onSubmit={submit} className="card space-y-3">
      <h2 className="card-title">Open a dispute</h2>
      <input className="input" placeholder="Transaction ID" required {...field("transaction_id")} />
      <input className="input" placeholder="Merchant" required {...field("merchant_name")} />
      <input className="input" placeholder="Amount (USD)" type="number" min="0.01" step="0.01" required {...field("amount")} />
      <select className="input" {...field("reason_code")}>
        {codes.map((c) => (
          <option key={c.reason_code} value={c.reason_code}>
            {c.reason_code} — {c.name}
          </option>
        ))}
      </select>
      {selected && selected.transaction_types.length > 0 && (
        <select className="input" value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
          <option value="">Transaction type: infer from documents</option>
          {selected.transaction_types.map((t) => (
            <option key={t} value={t}>
              {humanize(t)}
            </option>
          ))}
        </select>
      )}
      {error && <p className="text-sm text-red">{error}</p>}
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? "Opening…" : "Open dispute"}
      </button>
    </form>
  );
}
