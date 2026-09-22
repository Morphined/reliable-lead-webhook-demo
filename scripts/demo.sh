#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"

printf '\n1) Normal success\n'
curl -sS -X POST "$BASE/webhooks/leads" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-success-001' \
  -d '{"name":"Ada Buyer","email":"buyer@example.com","company":"example labs","source":"demo"}' | python -m json.tool

printf '\n2) Same request again: duplicate is returned without reprocessing\n'
curl -sS -X POST "$BASE/webhooks/leads" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-success-001' \
  -d '{"name":"Ada Buyer","email":"buyer@example.com","company":"example labs","source":"demo"}' | python -m json.tool

printf '\n3) Transient upstream failure: two failures, then success\n'
curl -sS -X POST "$BASE/webhooks/leads" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-retry-001' \
  -d '{"name":"Rita Retry","email":"retry@example.com","company":"retry labs","source":"demo"}' | python -m json.tool

printf '\n4) Terminal upstream failure: durable FAILED event + alert record\n'
curl -sS -X POST "$BASE/webhooks/leads" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-hardfail-001' \
  -d '{"name":"Frank Failure","email":"hardfail@example.com","company":"failure labs","source":"demo"}' | python -m json.tool || true
