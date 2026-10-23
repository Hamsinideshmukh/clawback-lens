"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { humanize, percent } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";

export function EvidenceChecklist({ data, onChange }: { data: CaseDetail; onChange: (c: CaseDetail) => void }) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const byKey = new Map(data.evidence.map((e) => [e.key, e]));
  const locked = data.status === "resolved";

  async function toggle(key: string, satisfied: boolean) {
    setPending(key);
    setError(null);
    try {
      onChange(await api.setEvidence(data.id, key, satisfied ? "missing" : "satisfied"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="card">
      <h2 className="card-title">
        Required evidence{data.transaction_type ? ` · ${humanize(data.transaction_type)}` : ""}
      </h2>
      <ul className="space-y-2">
        {data.required_evidence.map((key) => {
          const item = byKey.get(key);
          const satisfied = item?.status === "satisfied";
          return (
            <li key={key} className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={satisfied}
                disabled={locked || pending !== null}
                onChange={() => toggle(key, satisfied)}
              />
              <div>
                <p className={satisfied ? "font-medium text-navy" : "text-slate-600"}>{humanize(key)}</p>
                {satisfied && item && (
                  <p className="text-xs text-slate-500">
                    {item.source === "document" ? `from document · ${percent(item.confidence)} confidence` : "entered manually"}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
    </section>
  );
}
