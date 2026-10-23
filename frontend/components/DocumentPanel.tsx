"use client";

import { useEffect, useRef, useState } from "react";

import { DocumentViewer } from "@/components/DocumentViewer";
import { api } from "@/lib/api";
import { humanize, percent } from "@/lib/format";
import type { DocumentDetail, DocumentSummary } from "@/lib/types";

const PENDING = new Set(["queued", "processing"]);
const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp,image/tiff";

const SOURCE_STYLE: Record<string, string> = {
  ml: "bg-blue/10 text-blue",
  llm: "bg-purple-100 text-purple-700",
  vision: "bg-teal/10 text-teal",
};

interface Props {
  caseId: string;
  documents: DocumentSummary[];
  disabled: boolean;
  onChange: () => void;
}

export function DocumentPanel({ caseId, documents, disabled, onChange }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(documents.at(-1)?.id ?? null);
  const [loaded, setLoaded] = useState<DocumentDetail | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const selected = documents.find((d) => d.id === selectedId) ?? documents.at(-1);

  const completedId = selected?.status === "completed" ? selected.id : null;
  useEffect(() => {
    if (!completedId) return;
    let cancelled = false;
    api.getDocument(completedId).then((d) => !cancelled && setLoaded(d));
    return () => {
      cancelled = true;
    };
  }, [completedId]);
  // Only show analysis that belongs to the selected, completed document.
  const detail = loaded && loaded.id === completedId ? loaded : null;

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const created = await api.uploadDocument(caseId, file);
      setSelectedId(created.id);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <section className="card">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="card-title mb-0">Evidence documents</h2>
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        <button className="btn-primary" disabled={disabled || uploading} onClick={() => input.current?.click()}>
          {uploading ? "Uploading…" : "Upload scan or PDF"}
        </button>
      </div>
      {error && <p className="mb-3 text-sm text-red">{error}</p>}

      {documents.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          Upload a delivery receipt, boarding pass, refund confirmation or access log. The vision pipeline reads it,
          detects signatures and codes, and extracts evidence for the rule engine.
        </p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {documents.map((d) => (
              <button
                key={d.id}
                onClick={() => setSelectedId(d.id)}
                className={`btn text-xs ${d.id === selected?.id ? "bg-navy text-white" : "btn-ghost"}`}
              >
                {d.filename}
                <span className="ml-2 opacity-75">{PENDING.has(d.status) ? "analysing…" : d.status}</span>
              </button>
            ))}
          </div>

          {selected && PENDING.has(selected.status) && (
            <p className="animate-pulse text-sm text-slate-500">
              Running OCR, layout and signature detection on {selected.filename}…
            </p>
          )}
          {selected?.status === "failed" && <p className="text-sm text-red">{selected.error}</p>}

          {detail && (
            <div className="space-y-5">
              <DocumentViewer document={detail} />
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-700">Extracted evidence</h3>
                {detail.extraction?.candidates.length ? (
                  <ul className="space-y-2">
                    {detail.extraction.candidates.map((c) => (
                      <li key={c.key} className="rounded-lg bg-slate-50 p-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{humanize(c.key)}</span>
                          <span className="text-slate-500">{percent(c.confidence)}</span>
                          {c.sources.map((s) => (
                            <span key={s} className={`rounded px-1.5 py-0.5 text-xs ${SOURCE_STYLE[s] ?? ""}`}>
                              {s}
                            </span>
                          ))}
                        </div>
                        <blockquote className="mt-1 border-l-2 border-slate-300 pl-2 text-slate-600">
                          {c.citation}
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-500">No evidence relevant to this reason code was found.</p>
                )}
                <p className="mt-2 text-xs text-slate-400">
                  Models {detail.extraction?.model_version}
                  {detail.extraction?.llm_used ? " · LLM-assisted, grounded in OCR text" : " · local ONNX models"}
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
