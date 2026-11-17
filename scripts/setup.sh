#!/usr/bin/env bash
# Everything from scratch: certs, Konnect control plane (kongctl), gateway config (kongctl), stack, traffic.
# Safe to re-run. Needs: docker compose, kongctl (logged in or KONGCTL_DEFAULT_KONNECT_PAT), openssl, curl, python3.
set -euo pipefail
cd "$(dirname "$0")/.."
for t in docker kongctl openssl curl python3; do command -v $t >/dev/null || { echo "MISSING $t" >&2; exit 1; }; done
kongctl api get /v1/ai-gateways >/dev/null 2>&1 || { echo "kongctl is not authenticated: run 'kongctl login' or export KONGCTL_DEFAULT_KONNECT_PAT" >&2; exit 1; }
scripts/00-generate-certs.sh
scripts/01-bootstrap-gateway.sh
scripts/02-apply-config.sh
docker compose --profile traffic up -d --build
echo "==> waiting for the data plane to become healthy"
for i in $(seq 1 40); do
  [[ "$(docker compose ps --format '{{.Health}}' kong-data-plane)" == healthy ]] && break; sleep 3
done
echo "==> waiting for telemetry in Grafana (about 60 s)"; sleep 60
python3 scripts/validate-dashboard.py || true
echo
echo "Grafana:    http://localhost:${GRAFANA_PORT:-3000}/d/kong-ai-gateway-overview   (no login needed)"
echo "Gateway:    http://localhost:${GATEWAY_PORT:-18000}"
