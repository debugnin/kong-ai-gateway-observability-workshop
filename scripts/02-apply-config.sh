#!/usr/bin/env bash
# Applies auth, consumers, providers, models and the OpenTelemetry policy.
# Usage: scripts/02-apply-config.sh [plan]   ("plan" = dry run, changes nothing)
set -euo pipefail
cd "$(dirname "$0")/.."
# Generate one random API key per consumer, once. They go to .env (gitignored) and are written to Konnect as secrets.
for v in KEY_TEAM_A KEY_TEAM_B KEY_TEAM_C; do
  grep -q "^$v=." .env || { grep -v "^$v=" .env > .env.tmp || true; echo "$v=$(openssl rand -hex 16)" >> .env.tmp; mv .env.tmp .env; }
done
set -a; . ./.env; set +a
: "${AI_GATEWAY_ID:?run scripts/01-bootstrap-gateway.sh first}"
if [[ "${1:-}" == plan ]]; then kongctl plan --mode apply -f kongctl/01-config.yaml --base-dir . ; exit; fi
kongctl apply -f kongctl/01-config.yaml --base-dir . --auto-approve
