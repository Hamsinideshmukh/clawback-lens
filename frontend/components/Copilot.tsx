"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { CopilotReply } from "@/lib/types";

const SUGGESTIONS = ["Why is the case in this state?", "What evidence is missing?", "What did the documents show?"];

export function Copilot({ caseId }: { caseId: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<CopilotReply | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(message: string) {
    if (!message.trim()) return;
    setBusy(true);
    try {
      setAnswer(await api.copilot(caseId, message));
    } catch (err) {
      setAnswer({ reply: err instanceof Error ? err.message : "Copilot unavailable", tools_used: [], mode: "deterministic" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-3">
      <h2 className="card-title mb-0">Case copilot</h2>
      <div className="flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-200" onClick={() => ask(s)}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <input className="input" placeholder="Ask about this case" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button className="btn-primary" disabled={busy}>
          Ask
        </button>
      </form>
      {busy && <p className="animate-pulse text-sm text-slate-500">Consulting case tools…</p>}
      {answer && !busy && (
        <div className="rounded-lg bg-slate-50 p-3 text-sm">
          <p>{answer.reply}</p>
          <p className="mt-2 text-xs text-slate-400">
            {answer.mode === "llm" ? "LLM" : "Deterministic planner"} · tools: {answer.tools_used.join(", ") || "none"}
          </p>
        </div>
      )}
    </section>
  );
}
