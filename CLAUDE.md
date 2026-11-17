# CLAUDE.md

Guidance for AI agents working in this repo. Humans: start with [README.md](README.md) and [docs/architecture.md](docs/architecture.md).

## What this is

A hands-on workshop: a Kong AI Gateway 2.3 data plane (Docker) managed by a Konnect control plane (created with
`kongctl`) exports metrics, traces and logs through the **OpenTelemetry policy** to a Grafana LGTM stack
(`grafana/otel-lgtm`). A provisioned Grafana dashboard is modelled on the Konnect AI Manager overview page.
Providers, MCP servers and traffic are **mocks**; the gateway and telemetry pipeline are real.

## Rules for this repo

- **The repo is public and customer-facing.** Never commit `.env`, `certs/`, API keys, tokens, Konnect IDs, personal
  details, or customer, partner or engagement names. `.env` and `certs/` are gitignored; keep them that way.
- Do not commit, push or change repo visibility unless the user asks. Do not delete Konnect resources other than the
  workshop gateway `kong-aigw-observability`.
- Keep changes surgical and the docs in step with the code. A config change usually touches `kongctl/01-config.yaml`,
  `README.md` and `docs/architecture.md`.
- Say when something is observed versus documented. Unverified items stay in the README's "Not verified" list.

## Layout

```
kongctl/00-ai-gateway.yaml   control plane + DP certificate (created once)
kongctl/01-config.yaml       auth, consumers, groups, providers, models, MCP servers, OpenTelemetry policy
docker-compose.yml           lgtm, mock-llm, mcp-code, mcp-finance, kong-data-plane, loadgen (profile: traffic)
grafana/build_dashboard.py   SOURCE of the dashboard; writes grafana/dashboards/kong-ai-gateway.json
scripts/                     setup.sh, 00-/01-/02- steps, validate-dashboard.py, 99-teardown.sh
backends/llm-mock, backends/mcp-mock, loadgen/   Node mocks and traffic generator
```

## Run and verify

```bash
scripts/setup.sh                          # everything, idempotent; needs a logged-in kongctl (kongctl login or KONGCTL_DEFAULT_KONNECT_PAT)
scripts/02-apply-config.sh plan           # preview kongctl changes; "total_changes": 0 means no drift
scripts/02-apply-config.sh                # apply
python3 grafana/build_dashboard.py        # regenerate the dashboard JSON (Grafana reloads it in ~10 s)
python3 scripts/validate-dashboard.py     # runs every panel query against live Grafana; 0 problems expected
```

- Scripts `cd` to the repo root themselves, but other shell calls start wherever the session started: use paths relative to the repo root.
- Always `plan` before `apply`. Never hand-edit `kong-ai-gateway.json`; edit `build_dashboard.py`.
- Grafana is at http://localhost:3000 (admin/admin, anonymous Viewer). Query datasources through its proxy, for example
  `curl -u admin:admin localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query ...` (uids: `prometheus`, `loki`, `tempo`).
- Dashboard changes: verify with `validate-dashboard.py`, and look at the rendered page when layout matters.
- Telemetry takes about 60 s to appear after start. "Previous period" tiles stay empty until the stack has run twice the selected range.

## Things that are easy to get wrong

**kongctl**
- Child resources point at the gateway with `ai_gateway: !lookup { id: !env AI_GATEWAY_ID }` (`AI_GATEWAY_ID` is written to `.env` by `01-bootstrap-gateway.sh`).
- Secrets use `!secret` and are write-only. Consumer API keys are generated into `.env` by `02-apply-config.sh`.
- "managed_by drift" warnings on consumer credentials are harmless kongctl metadata notes.
- Consumer API keys use consumer `type: api-key` with credentials of `type: api-key`.
- `kongctl explain <resource>` shows the declarative schema; the plan does not validate every field, the apply does.
- MCP server `access` requires `acl_attribute_type`. **ACLs matched consumer group names**, not consumer names, `custom_id` or UUID (observed).
  An ACL takes exactly one of `allow` / `deny`; an empty `allow` allowed everyone.

**Telemetry**
- OTLP names become Prometheus names with underscores plus a suffix (`gen_ai.client.token.usage` → `gen_ai_client_token_usage_total`;
  histograms get `_seconds_bucket/_count/_sum`). Attributes become labels (`kong.auth.consumer.name` → `kong_auth_consumer_name`).
- The `gen_ai_token_type="total"` series equals input plus output: never add it to `input` and `output`.
- Successful requests have an empty `error_type` label, so errors are `error_type!=""`.
- `kong_dp_cluster_cert_expiry_seconds` is an absolute timestamp; subtract `time()`.
- The collector in `grafana/otel-lgtm` sends metrics to **Prometheus** (OTLP endpoint), not Mimir.
- Loki fields such as `log_type` are structured metadata: filter with `| log_type="access"`, not in the stream selector.
- In 2.3, OTLP **access logs** only appeared for responses Kong itself produces (401, 403, 404), not for proxied LLM requests. Use traces and metrics for AI traffic.
- `kong.gen_ai.mcp.acl.allowed/denied` produced no series with server-level ACLs, so no panel uses them.

**Docs and wording**
- `docs/architecture.md` has Mermaid diagrams. After editing them, check they parse (GitHub shows a broken box on a syntax error).
- Costs use invented prices and token counts come from the mock; do not present dashboard numbers as real usage.

## Known gaps

A full teardown followed by `scripts/setup.sh` on a fresh Konnect gateway has not been run since MCP servers and groups were added.
See "Observed behaviour and caveats" in the README for the rest.
