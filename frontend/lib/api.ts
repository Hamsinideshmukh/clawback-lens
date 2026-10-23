import type {
  CaseDetail,
  CaseList,
  CaseStatus,
  CopilotReply,
  DocumentDetail,
  DocumentSummary,
  Outcome,
  ReasonCode,
  TimelineEvent,
} from "@/lib/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listCases: (status?: CaseStatus) => request<CaseList>(`/api/v1/cases${status ? `?status=${status}` : ""}`),
  getCase: (id: string) => request<CaseDetail>(`/api/v1/cases/${id}`),
  createCase: (body: {
    transaction_id: string;
    merchant_name: string;
    amount: string;
    reason_code: string;
    transaction_type?: string | null;
  }) => request<CaseDetail>("/api/v1/cases", { method: "POST", body: JSON.stringify(body) }),
  setEvidence: (id: string, key: string, status: "satisfied" | "missing") =>
    request<CaseDetail>(`/api/v1/cases/${id}/evidence/${key}`, { method: "PUT", body: JSON.stringify({ status }) }),
  decide: (id: string, outcome: Outcome, note?: string) =>
    request<CaseDetail>(`/api/v1/cases/${id}/decision`, { method: "POST", body: JSON.stringify({ outcome, note }) }),
  timeline: (id: string) => request<TimelineEvent[]>(`/api/v1/cases/${id}/timeline`),
  copilot: (id: string, message: string) =>
    request<CopilotReply>(`/api/v1/cases/${id}/copilot`, { method: "POST", body: JSON.stringify({ message }) }),
  uploadDocument: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentSummary>(`/api/v1/cases/${id}/documents`, { method: "POST", body: form });
  },
  getDocument: (id: string) => request<DocumentDetail>(`/api/v1/documents/${id}`),
  previewUrl: (id: string) => `${API_URL}/api/v1/documents/${id}/preview`,
  reasonCodes: () => request<ReasonCode[]>("/api/v1/reason-codes"),
};
