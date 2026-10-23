import { formatTime } from "@/lib/format";
import type { TimelineEvent } from "@/lib/types";

const ACTOR_COLOR: Record<string, string> = {
  vision: "bg-teal",
  ml: "bg-blue",
  llm: "bg-purple-500",
  rule_engine: "bg-navy",
  workflow: "bg-gold",
  sla_engine: "bg-red",
};

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <section className="card">
      <h2 className="card-title">Audit timeline</h2>
      <ol className="space-y-3">
        {[...events].reverse().map((e, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${ACTOR_COLOR[e.actor.split("+")[0]] ?? "bg-slate-400"}`} />
            <div>
              <p className="text-slate-700">{e.description}</p>
              <p className="text-xs text-slate-400">
                {e.actor} · {formatTime(e.occurred_at)}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
