"use client";

import { useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { humanize, timeLeft } from "@/lib/format";
import type { CaseDetail, Outcome } from "@/lib/types";

const VERDICT_LABEL: Record<string, string> = {
  auto_resolve_merchant: "Merchant evidence satisfies the rule",
  auto_resolve_card_member: "Favours the card member",
  insufficient_evidence: "Insufficient evidence",
  escalate_to_human: "Needs human review",
};

export function VerdictCard({ data, onChange }: { data: CaseDetail; onChange: (c: CaseDetail) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const evaluation = data.latest_evaluation;

  async function decide(outcome: Outcome) {
    setBusy(true);
    try {
      onChange(await api.decide(data.id, outcome, note || undefined));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="card-title mb-0">Rule engine verdict</h2>
        <StatusBadge status={data.status} outcome={data.outcome} />
      </div>
      {evaluation ? (
        <>
          <p className="text-lg font-semibold text-navy">{VERDICT_LABEL[evaluation.status] ?? humanize(evaluation.status)}</p>
          <p className="text-sm text-slate-600">{evaluation.explanation}</p>
        </>
      ) : (
        <p className="text-sm text-slate-500">No evidence evaluated yet.</p>
      )}
      {data.status === "open" && <p className="text-xs text-slate-500">Merchant response window: {timeLeft(data.respond_by)}</p>}
      {data.retrieval_requests.map((r) => (
        <p key={r.id} className="text-xs text-slate-500">
          Retrieval Request (RC {r.reason_code}): {r.status}
          {r.status === "pending" && ` · ${timeLeft(r.deadline)}`}
        </p>
      ))}

      {data.status === "escalated" && (
        <div className="space-y-2 border-t border-slate-100 pt-3">
          <p className="text-sm font-medium">Analyst decision</p>
          <textarea className="input" rows={2} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <button className="btn-primary flex-1" disabled={busy} onClick={() => decide("merchant")}>
              Merchant wins
            </button>
            <button className="btn-ghost flex-1" disabled={busy} onClick={() => decide("card_member")}>
              Card member wins
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
