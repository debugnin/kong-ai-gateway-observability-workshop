#!/usr/bin/env bash
# Stops the stack and deletes ONLY the workshop gateway (looked up by name) from Konnect.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile traffic down -v || true
ID="$(kongctl get ai-gateway kong-aigw-observability --output json --jq '.id' --jq-raw-output 2>/dev/null || true)"
if [[ -n "$ID" ]]; then
  read -r -p "Delete AI Gateway 'kong-aigw-observability' ($ID) from Konnect? [y/N] " a
  [[ "$a" == y ]] && kongctl api delete "/v1/ai-gateways/$ID" && echo deleted
fi
rm -f .env certs/data-plane.key certs/data-plane.crt
