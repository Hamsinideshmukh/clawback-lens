#!/usr/bin/env bash
# Creates demo disputes and uploads the sample scans through the public API.
# Works against local compose or a deployment:  scripts/demo.sh https://clawback-lens-api.onrender.com
set -euo pipefail

API="${1:-http://localhost:8000}/api/v1"
SAMPLES="$(cd "$(dirname "$0")/../samples" && pwd)"

create_case() {  # merchant amount reason_code -> case id
  curl -fsS -X POST "$API/cases" -H 'content-type: application/json' \
    -d "{\"transaction_id\":\"txn_$RANDOM\",\"merchant_name\":\"$1\",\"amount\":\"$2\",\"reason_code\":\"$3\"}" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])'
}

upload() {  # case id, sample file
  curl -fsS -o /dev/null -X POST "$API/cases/$1/documents" -F "file=@$SAMPLES/$2;type=image/jpeg"
  echo "  uploaded $2"
}

echo "Seeding demo disputes at $API"
upload "$(create_case "Orbit Retail" 249.99 4554)" delivery_receipt.jpg
upload "$(create_case "SkyBridge Airways" 612.00 4554)" boarding_pass.jpg
upload "$(create_case "Northwind Goods" 86.40 4530)" refund_confirmation.jpg
upload "$(create_case "Pixel Media" 39.99 4554)" access_log.jpg
case_id="$(create_case "Lumen Electronics" 1299.00 4553)"
curl -fsS -o /dev/null -X PUT "$API/cases/$case_id/evidence/description_match_proof" \
  -H 'content-type: application/json' -d '{"status":"satisfied"}'
echo "  judgment-heavy case escalated for analyst review"
case_id="$(create_case "Atlas Outfitters" 74.99 4512)"
curl -fsS -o /dev/null -X POST "$API/cases/$case_id/retrieval-requests"
echo "  retrieval request opened (SLA clock running)"
echo "Done. Documents are processed by the worker within a few seconds."
