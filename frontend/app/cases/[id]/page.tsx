"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Copilot } from "@/components/Copilot";
import { DocumentPanel } from "@/components/DocumentPanel";
import { EvidenceChecklist } from "@/components/EvidenceChecklist";
import { Timeline } from "@/components/Timeline";
import { VerdictCard } from "@/components/VerdictCard";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import type { CaseDetail, TimelineEvent } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

const hasPendingDocuments = (c: CaseDetail) => c.documents.some((d) => d.status === "queued" || d.status === "processing");

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const { data, error, refresh, setData } = usePolling(() => api.getCase(params.id), hasPendingDocuments);
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  const loadTimeline = useCallback(() => api.timeline(params.id).then(setEvents).catch(() => undefined), [params.id]);
  useEffect(() => void loadTimeline(), [data, loadTimeline]);

  if (error) return <p className="text-red">{error}</p>;
  if (!data) return <p className="animate-pulse text-slate-500">Loading case…</p>;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue hover:underline">
          ← All cases
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-navy">
          {data.merchant_name} · {money(data.amount, data.currency)}
        </h1>
        <p className="text-sm text-slate-500">
          RC {data.reason_code} — {data.reason_name} · transaction {data.transaction_id}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <DocumentPanel
            caseId={data.id}
            documents={data.documents}
            disabled={data.status === "resolved"}
            onChange={() => void refresh()}
          />
          <Timeline events={events} />
        </div>
        <div className="space-y-6">
          <VerdictCard data={data} onChange={setData} />
          <EvidenceChecklist data={data} onChange={setData} />
          <Copilot caseId={data.id} />
        </div>
      </div>
    </div>
  );
}
