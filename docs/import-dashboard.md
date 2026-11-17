# Import the dashboard into your own Grafana

The dashboard **Kong AI Gateway: Overview** is a single JSON file that you can import into any Grafana:

**[`grafana/dashboards/kong-ai-gateway.json`](../grafana/dashboards/kong-ai-gateway.json)**

It does not depend on the rest of this workshop. It needs a Kong AI Gateway 2.x that exports telemetry with the
OpenTelemetry policy, and datasources that hold that telemetry. The datasources are **dashboard variables**, so there
are no UIDs to edit.

> **What has been tested.** The file was imported and checked against the `grafana/otel-lgtm` stack used in this
> workshop (Grafana 13.3.0, Prometheus, Tempo, Loki) with AI Gateway 2.3.0. It has not been tested against other
> Grafana versions, Mimir, Grafana Cloud or other collectors. The checklist at the end helps you find differences quickly.

## 1. What you need

| Need | Used by | Required? |
|---|---|---|
| Kong AI Gateway 2.x with the **OpenTelemetry policy** exporting **metrics** (settings below) | Every panel except Traces and logs | Yes |
| A Prometheus-compatible metrics store (Prometheus, Mimir, ...) holding those metrics | Every panel except Traces and logs | Yes |
| Tempo receiving the policy's traces | "Recent LLM traces" panel | Optional |
| Loki receiving the policy's logs | The three log panels | Optional |
| An MCP server on the gateway | The MCP row | Optional (the row is empty without one) |

Optional rows simply show no data if their datasource is missing; the rest of the dashboard is unaffected.

### OpenTelemetry policy settings

These are the settings used by this workshop (`kongctl/01-config.yaml`). Replace the endpoints with your collector's OTLP/HTTP address.

```yaml
ai_gateway_policies:
  - ref: opentelemetry
    ai_gateway: !lookup { id: !env AI_GATEWAY_ID }
    name: opentelemetry
    type: opentelemetry
    global: true
    config:
      metrics:
        endpoint: http://<collector>:4318/v1/metrics
        push_interval: 10
        enable_ai_metrics: true
        enable_latency_metrics: true
        enable_request_metrics: true
        enable_bandwidth_metrics: true
        enable_consumer_attribute: true
      traces_endpoint: http://<collector>:4318/v1/traces
      sampling_rate: 1
      logs_endpoint: http://<collector>:4318/v1/logs
      access_logs:
        endpoint: http://<collector>:4318/v1/logs
      resource_attributes:
        service.name: kong-ai-gateway
```

What the flags do, according to the AI Gateway documentation:

| Flag | Effect | Dashboard panels that rely on it |
|---|---|---|
| `enable_ai_metrics` | Turns on all `gen_ai.*` metrics | Tokens, cost, TTFT, TPOT, top consumers |
| `enable_latency_metrics` | Required for `gen_ai.server.request.duration` | LLM latency, **request count and error rate** (both are derived from this metric) |
| `enable_request_metrics` | Required for the `error.type` attribute, and adds request count metrics | Error rate, success rate, HTTP status panel |
| `enable_consumer_attribute` | Adds `kong.auth.consumer.name` | Users (consumers), model usage by user |
| `enable_bandwidth_metrics` | Adds request and response size metrics | Request / response size |

Cost needs `input_cost` and `output_cost` (dollars per million tokens) on each AI model target; without them the Costs
panels stay at zero. The Cached tokens tile only shows data when the provider reports cached usage.
Which flag controls the `kong_latency_*` metrics was not checked; this workshop turns them all on.

## 2. Import

### Option A: Grafana UI

1. Download the JSON file (for example `curl -LO https://raw.githubusercontent.com/debugnin/kong-ai-gateway-observability-workshop/main/grafana/dashboards/kong-ai-gateway.json`).
2. In Grafana: **Dashboards → New → Import → Upload dashboard JSON file**, then **Import**.
3. At the top of the dashboard, set the **Prometheus**, **Loki** and **Tempo** pickers to your datasources. They are variables, so the choice applies to the whole dashboard.
4. Set **OTel service.name** to the `service.name` you configured in the policy's `resource_attributes` (default `kong-ai-gateway`).

### Option B: Grafana HTTP API

Use a service account token with permission to create dashboards:

```bash
GRAFANA=https://grafana.example.com
TOKEN=<service-account-token>
jq '{dashboard: ., overwrite: true}' kong-ai-gateway.json |
  curl -s -X POST "$GRAFANA/api/dashboards/db" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-
```

The dashboard keeps the UID `kong-ai-gateway-overview`. With `overwrite: true` an existing dashboard with that UID is replaced.
Change `uid` in the file first if you want to keep an existing copy.

### Option C: file provisioning

Copy the JSON into a directory that a Grafana dashboard provider reads. This workshop does exactly that:
[`grafana/provisioning/dashboards.yaml`](../grafana/provisioning/dashboards.yaml) is the provider and
`docker-compose.yml` mounts `grafana/dashboards/` into the container. Grafana reloads changed files by itself.

## 3. Variables at the top of the dashboard

| Variable | Meaning |
|---|---|
| **Prometheus**, **Loki**, **Tempo** | Datasource pickers. Choose the datasources that hold the gateway's telemetry |
| **OTel service.name** | Used by the Loki log panels (`service_name`) and the Tempo trace panel (`resource.service.name`) |
| **Providers**, **AI Gateway models**, **Consumers** | Filters, like the Konnect AI Manager filters. They are filled from the metrics and apply to every metrics panel |

The metrics panels do not filter on resource attributes such as `job` or `service_name`, so you do not need to promote
resource attributes to metric labels. If several gateways write to the same Prometheus, add a filter on a label that
identifies yours (for example `kong_konnect_cp_id`, which this workshop's metrics carried) by editing the dashboard or
`grafana/build_dashboard.py`.

## 4. Check that it works

Run these in **Explore** on your Prometheus datasource. Each should return series after a minute of traffic:

```promql
gen_ai_client_token_usage_total
gen_ai_server_request_duration_seconds_count
kong_gen_ai_llm_cost_total
```

If you can run this workshop's checker against your Grafana, it executes every panel query and reports errors and empty panels.
It uses the datasource UIDs `prometheus`, `loki` and `tempo` and anonymous access, so adjust the script if your Grafana differs:
`python3 scripts/validate-dashboard.py https://grafana.example.com`.

## 5. No data: checklist

| Symptom | Likely cause and check |
|---|---|
| Every panel says "datasource not found" or is empty | The three datasource pickers at the top are not set to real datasources |
| Metrics panels empty, `gen_ai_*` not found in Explore | The policy is not applied (check it is `global: true` or attached to the model), the metrics endpoint is wrong, or `enable_ai_metrics` is off. Search Explore for `gen_ai` to see what arrived |
| Series exist under different names, for example with dots or without `_total` / `_seconds` | Your store translates OTLP names differently from the Prometheus default used here. Find the real names in Explore and update the queries in `grafana/build_dashboard.py`, then regenerate the JSON |
| Latency and request panels empty, tokens fine | `enable_latency_metrics` is off |
| Error panels always 0 | `enable_request_metrics` is off, so `error_type` is never set |
| Users panels are empty or show a single unnamed entry | `enable_consumer_attribute` is off, or the requests are not authenticated to a consumer |
| Cost is 0 | `input_cost` / `output_cost` are not set on the model targets |
| Log panels empty | Logs are not reaching Loki, or your Loki does not turn the OTLP `service.name` into a `service_name` label, or **OTel service.name** does not match. Also see the access-log note below |
| Trace table empty | Traces are not reaching Tempo, or **OTel service.name** does not match |
| MCP row empty | No MCP server is configured on the gateway |
| "Previous period" shows nothing | The data does not yet cover twice the selected time range |

**Access logs.** In this workshop (AI Gateway 2.3.0) the OTLP access logs only appeared for responses Kong itself produces
(for example 401 or 403), not for requests proxied to an LLM. The "access logs, errors only" panel reflects that. This is an
observation and should be confirmed with your Kong contact.

## 6. Changing the dashboard

The JSON is generated by [`grafana/build_dashboard.py`](../grafana/build_dashboard.py). To change panels or queries, edit the
script and run `python3 grafana/build_dashboard.py`, then re-import the JSON. Editing in the Grafana UI also works; export
with **Share → Export → Export for sharing externally** if you need a copy with datasource inputs.
