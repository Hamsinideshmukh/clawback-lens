"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { humanize, percent } from "@/lib/format";
import type { Box, DocumentDetail } from "@/lib/types";

const LAYERS = {
  text: { label: "OCR lines", stroke: "#2E5EAA" },
  signature: { label: "Signatures", stroke: "#1F8A70" },
  code: { label: "Codes", stroke: "#C99A2E" },
} as const;
type Layer = keyof typeof LAYERS;
const STAGES = ["decode", "quality", "binarize", "deskew", "ocr", "codes", "signatures", "preview"];

function Rect({ box, layer }: { box: Box; layer: Layer }) {
  const { stroke } = LAYERS[layer];
  return (
    <rect
        x={box.x * 100}
        y={box.y * 100}
        width={box.w * 100}
        height={box.h * 100}
        fill={layer === "text" ? "transparent" : `${stroke}22`}
        stroke={stroke}
        strokeWidth={layer === "text" ? 0.15 : 0.35}
      vectorEffect="non-scaling-stroke"
    />
  );
}

// Labels are HTML, not SVG text, so they are not stretched by the non-uniform viewBox.
function Label({ box, layer, text }: { box: Box; layer: Layer; text: string }) {
  return (
    <span
      className="absolute -translate-y-full rounded px-1 text-[10px] font-semibold text-white"
      style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, background: LAYERS[layer].stroke }}
    >
      {text}
    </span>
  );
}

export function DocumentViewer({ document }: { document: DocumentDetail }) {
  const [visible, setVisible] = useState<Record<Layer, boolean>>({ text: true, signature: true, code: true });
  const page = document.analysis?.pages[0];
  if (!page) return null;

  const timings = Object.entries(document.analysis?.timings_ms ?? {}).sort(
    ([a], [b]) => STAGES.indexOf(a) - STAGES.indexOf(b),
  );
  const totalMs = timings.reduce((sum, [, ms]) => sum + ms, 0);
  const flags = Object.entries(page.quality).filter(([, v]) => v === true);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
      <div>
        <div className="mb-2 flex flex-wrap gap-2">
          {(Object.keys(LAYERS) as Layer[]).map((layer) => (
            <label key={layer} className="flex items-center gap-1.5 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={visible[layer]}
                onChange={() => setVisible({ ...visible, [layer]: !visible[layer] })}
              />
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LAYERS[layer].stroke }} />
              {LAYERS[layer].label}
            </label>
          ))}
        </div>
        <div className="relative overflow-hidden rounded-lg border border-slate-200">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={api.previewUrl(document.id)} alt={`Deskewed scan of ${document.filename}`} className="w-full" />
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
            {visible.text && page.lines.map((line, i) => <Rect key={i} box={line.box} layer="text" />)}
            {visible.signature && page.signatures.map((s, i) => <Rect key={i} box={s.box} layer="signature" />)}
            {visible.code && page.codes.map((c, i) => <Rect key={i} box={c.box} layer="code" />)}
          </svg>
          {visible.signature &&
            page.signatures.map((s, i) => (
              <Label key={i} box={s.box} layer="signature" text={`signature ${percent(s.score)}`} />
            ))}
          {visible.code && page.codes.map((c, i) => <Label key={i} box={c.box} layer="code" text={c.kind} />)}
        </div>
      </div>

      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-slate-500">Document type</dt>
          <dd className="font-medium">
            {humanize(document.doc_type ?? "unknown")} · {percent(document.doc_type_confidence)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">OCR confidence</dt>
          <dd className="font-medium">
            {percent(document.ocr_confidence)} over {page.lines.length} lines
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Deskew</dt>
          <dd className="font-medium">{page.skew_degrees.toFixed(1)}°</dd>
        </div>
        {page.codes.map((c, i) => (
          <div key={i}>
            <dt className="text-slate-500">Decoded {c.kind}</dt>
            <dd className="break-all font-mono text-xs">{c.payload}</dd>
          </div>
        ))}
        {flags.length > 0 && (
          <div>
            <dt className="text-slate-500">Quality warnings</dt>
            <dd className="text-amber-700">{flags.map(([k]) => humanize(k)).join(", ")}</dd>
          </div>
        )}
        <div>
          <dt className="mb-1 text-slate-500">Pipeline · {Math.round(totalMs)} ms</dt>
          <dd className="space-y-1">
            {timings.map(([stage, ms]) => (
              <div key={stage} className="flex items-center gap-2 text-xs">
                <span className="w-16 text-slate-500">{stage}</span>
                <span className="h-1.5 rounded bg-blue" style={{ width: `${Math.max(2, (ms / totalMs) * 100)}%` }} />
                <span className="text-slate-400">{Math.round(ms)}</span>
              </div>
            ))}
          </dd>
        </div>
      </dl>
    </div>
  );
}
