#!/usr/bin/env bash
# Self-signed cert the data plane uses to authenticate to Konnect over mTLS. Only the .crt goes to Konnect.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs
if [[ -f certs/data-plane.key && -f certs/data-plane.crt ]]; then echo "certs already exist; delete to regenerate"; exit 0; fi
openssl req -new -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=observability-workshop-data-plane/C=US" \
  -keyout certs/data-plane.key -out certs/data-plane.crt
chmod 640 certs/data-plane.key
echo "Generated certs/data-plane.{crt,key}"
