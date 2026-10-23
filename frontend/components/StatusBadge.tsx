import type { CaseStatus, Outcome } from "@/lib/types";

const STYLES: Record<CaseStatus, string> = {
  open: "bg-blue/10 text-blue",
  escalated: "bg-gold/15 text-amber-700",
  resolved: "bg-teal/10 text-teal",
};

export function StatusBadge({ status, outcome }: { status: CaseStatus; outcome?: Outcome | null }) {
  const label = status === "resolved" && outcome ? `resolved · ${outcome.replace("_", " ")}` : status;
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>{label}</span>;
}
