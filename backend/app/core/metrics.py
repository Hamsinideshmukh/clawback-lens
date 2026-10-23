"""Prometheus metrics exposed at /metrics."""

from prometheus_client import Counter, Histogram

HTTP_LATENCY = Histogram("clawback_http_request_seconds", "HTTP request latency", ["method", "route", "status"])
PIPELINE_STAGE_SECONDS = Histogram(
    "clawback_pipeline_stage_seconds",
    "Document pipeline stage latency",
    ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
DOCUMENTS_PROCESSED = Counter("clawback_documents_processed_total", "Documents processed", ["status", "doc_type"])
OCR_CONFIDENCE = Histogram(
    "clawback_ocr_confidence", "Mean OCR confidence per document", buckets=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0)
)
EVIDENCE_EXTRACTED = Counter("clawback_evidence_extracted_total", "Evidence candidates accepted", ["source"])
LLM_REQUESTS = Counter("clawback_llm_requests_total", "LLM calls", ["purpose", "outcome"])
JOBS = Counter("clawback_jobs_total", "Background jobs", ["kind", "outcome"])
VERDICTS = Counter("clawback_verdicts_total", "Rule engine verdicts", ["status"])
