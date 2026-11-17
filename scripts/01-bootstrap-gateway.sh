#!/usr/bin/env bash
# Creates the AI Gateway control plane + DP certificate in Konnect with kongctl, then records endpoints in .env.
# Auth: kongctl uses KONGCTL_DEFAULT_KONNECT_PAT or your `kongctl login` session. Nothing secret is written to .env.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f certs/data-plane.crt ]] || { echo "Run scripts/00-generate-certs.sh first" >&2; exit 1; }
[[ -f .env ]] || cp .env.example .env
echo "==> kongctl apply kongctl/00-ai-gateway.yaml"
kongctl apply -f kongctl/00-ai-gateway.yaml --base-dir . --auto-approve
J() { kongctl get ai-gateway kong-aigw-observability --output json --jq "$1" --jq-raw-output; }
ID="$(J '.id')"
CP="$(J '.endpoints.configuration | sub("^https://"; "") | sub(":443$"; "")')"
TP="$(J '.endpoints.telemetry | sub("^https://"; "") | sub(":443$"; "")')"
grep -v -E '^(AI_GATEWAY_ID|AIGW_CONTROL_PLANE|AIGW_TELEMETRY)=' .env > .env.tmp || true
printf 'AI_GATEWAY_ID=%s\nAIGW_CONTROL_PLANE=%s\nAIGW_TELEMETRY=%s\n' "$ID" "$CP" "$TP" >> .env.tmp
mv .env.tmp .env
echo "==> .env updated (AI_GATEWAY_ID=$ID)"
