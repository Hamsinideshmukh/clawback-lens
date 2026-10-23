// Mirrors backend/app/schemas/case.py.

export type CaseStatus = "open" | "escalated" | "resolved";
export type Outcome = "merchant" | "card_member";
export type DocumentStatus = "queued" | "processing" | "completed" | "failed";

export interface Evidence {
  key: string;
  status: "satisfied" | "missing";
  source: "manual" | "document";
  confidence: number;
  citation: string | null;
  document_id: string | null;
  submitted_at: string;
}

export interface Evaluation {
  reason_code: string;
  status: string;
  satisfied: string[];
  missing: string[];
  contestability: string | null;
  explanation: string;
  evaluated_at: string;
}

export interface DocumentSummary {
  id: string;
  case_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  doc_type: string | null;
  doc_type_confidence: number | null;
  ocr_confidence: number | null;
  error: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PageAnalysis {
  index: number;
  width: number;
  height: number;
  skew_degrees: number;
  quality: Record<string, number | boolean>;
  lines: { text: string; confidence: number; box: Box }[];
  signatures: { box: Box; score: number }[];
  codes: { kind: string; payload: string; box: Box }[];
}

export interface EvidenceCandidate {
  key: string;
  confidence: number;
  citation: string;
  sources: string[];
}

export interface DocumentDetail extends DocumentSummary {
  ocr_text: string | null;
  analysis: { pages: PageAnalysis[]; timings_ms: Record<string, number> } | null;
  extraction: {
    doc_type: string;
    transaction_type: string | null;
    candidates: EvidenceCandidate[];
    model_version: string;
    llm_used: boolean;
  } | null;
}

export interface CaseSummary {
  id: string;
  transaction_id: string;
  merchant_name: string;
  amount: string;
  currency: string;
  reason_code: string;
  transaction_type: string | null;
  status: CaseStatus;
  outcome: Outcome | null;
  respond_by: string;
  created_at: string;
}

export interface CaseDetail extends CaseSummary {
  reason_name: string;
  required_evidence: string[];
  evidence: Evidence[];
  documents: DocumentSummary[];
  retrieval_requests: { id: string; reason_code: string; deadline: string; status: string }[];
  latest_evaluation: Evaluation | null;
}

export interface CaseList {
  items: CaseSummary[];
  total: number;
  status_counts: Partial<Record<CaseStatus, number>>;
}

export interface ReasonCode {
  reason_code: string;
  name: string;
  always_escalate: boolean;
  transaction_types: string[];
  evidence: Record<string, string>;
}

export interface TimelineEvent {
  actor: string;
  event_type: string;
  description: string;
  occurred_at: string;
}

export interface CopilotReply {
  reply: string;
  tools_used: string[];
  mode: "llm" | "deterministic";
}
