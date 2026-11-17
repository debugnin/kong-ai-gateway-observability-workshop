#!/usr/bin/env python3
"""Generates grafana/dashboards/kong-ai-gateway.json.

Layout mirrors the Konnect AI Manager overview page (Key metrics, Top consumers, Performance, Costs,
Models, MCP) and adds two rows Konnect does not have: Gateway health and Traces & Logs.
Run:  python3 grafana/build_dashboard.py
"""
import json, pathlib

# Datasources are dashboard variables (ds_prometheus / ds_loki / ds_tempo) so the JSON imports into any Grafana.
PROM = {"type": "prometheus", "uid": "${ds_prometheus}"}
LOKI = {"type": "loki", "uid": "${ds_loki}"}
TEMPO = {"type": "tempo", "uid": "${ds_tempo}"}

# Dashboard-wide filters (the "All providers / All models / All agents" filters of the Konnect page).
F = 'gen_ai_provider_name=~"$provider",gen_ai_request_model=~"$model",kong_auth_consumer_name=~"$consumer"'
DUR = "gen_ai_server_request_duration_seconds"
REQ = f"{DUR}_count"
TOK = "gen_ai_client_token_usage_total"
COST = "kong_gen_ai_llm_cost_total"

_id = [0]
panels = []
_y = [0]


def nid():
    _id[0] += 1
    return _id[0]


def tgt(expr, legend="", ref="A", instant=False, fmt=None, ds=PROM):
    t = {"datasource": ds, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update({"instant": True, "range": False})
    else:
        t.update({"range": True})
    if fmt:
        t["format"] = fmt
    return t


def row(title, collapsed=False):
    p = {"id": nid(), "type": "row", "title": title, "collapsed": collapsed,
         "gridPos": {"h": 1, "w": 24, "x": 0, "y": _y[0]}, "panels": []}
    _y[0] += 1
    panels.append(p)
    return p


def panel(kind, title, x, w, h, targets, unit=None, desc="", ds=PROM, options=None, custom=None,
          overrides=None, thresholds=None, transformations=None, minv=None, maxv=None, decimals=None, into=None, color=None):
    p = {"id": nid(), "type": kind, "title": title, "description": desc, "datasource": ds,
         "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]}, "targets": targets,
         "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "custom": custom or {},
                                      "thresholds": thresholds or {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}},
                         "overrides": overrides or []},
         "options": options or {}}
    d = p["fieldConfig"]["defaults"]
    if color:
        d["color"] = color
    if unit:
        d["unit"] = unit
    if minv is not None:
        d["min"] = minv
    if maxv is not None:
        d["max"] = maxv
    if decimals is not None:
        d["decimals"] = decimals
    if transformations:
        p["transformations"] = transformations
    (into["panels"] if into else panels).append(p)
    return p


def next_row(h):
    _y[0] += h


# ---------- helpers -------------------------------------------------------------------------------------------
def q(metric_expr, by=""):
    return metric_expr


def pct(p, by="", rng="$__rate_interval", metric=DUR, flt=F):
    g = f"sum by (le{',' + by if by else ''})"
    return f'histogram_quantile({p}, {g}(rate({metric}_bucket{{{flt}}}[{rng}])))'


def tiles(title, cur, unit, desc, x, w=4, decimals=None, thresholds=None, h=4):
    """Stat tile: current period vs previous period of the same length (like the Konnect 'vs previous' compare)."""
    prev = cur.replace("[$__range]", "[$__range] offset $__range")
    panel("stat", title, x, w, h,
          [tgt(cur, "Now", "A", instant=True), tgt(prev, "Previous period", "B", instant=True)],
          unit=unit, desc=desc, decimals=decimals, thresholds=thresholds,
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "textMode": "value_and_name", "colorMode": "value", "graphMode": "none",
                   "orientation": "vertical", "justifyMode": "center"},
          overrides=[{"matcher": {"id": "byName", "options": "Previous period"},
                      "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "text"}}]}])


def ts(title, x, w, h, targets, unit=None, desc="", stack=False, bars=False, fill=15, minv=None, maxv=None,
       overrides=None, into=None, thresholds=None):
    custom = {"lineWidth": 1, "fillOpacity": fill, "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"},
              "drawStyle": "bars" if bars else "line"}
    panel("timeseries", title, x, w, h, targets, unit=unit, desc=desc, custom=custom, minv=minv, maxv=maxv,
          options={"legend": {"displayMode": "list", "placement": "bottom", "calcs": []},
                   "tooltip": {"mode": "multi", "sort": "desc"}}, overrides=overrides, into=into, thresholds=thresholds)


def top(title, by, x, metric_expr, unit="short", w=6, desc=""):
    panel("bargauge", title, x, w, 7,
          [tgt(f"topk(5, sum by ({by}) ({metric_expr}))", "{{" + by + "}}", instant=True)],
          unit=unit, desc=desc,
          color={"mode": "fixed", "fixedColor": "blue"},
          options={"displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True,
                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "namePlacement": "top"})


# =========================================================================================================
# KEY METRICS
# =========================================================================================================
row("Key metrics (selected range vs the previous range of the same length)")
INC_REQ = f"sum(increase({REQ}{{{F}}}[$__range]))"
ERR_NUM = f'sum(increase({REQ}{{{F},error_type!=""}}[$__range]))'
tiles("LLM latency (p95)", f"histogram_quantile(0.95, sum by (le)(increase({DUR}_bucket{{{F}}}[$__range])))", "s",
      "p95 of gen_ai.server.request.duration: time from request received to response complete, as seen by the gateway.", 0,
      decimals=2, thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 3}, {"color": "red", "value": 8}]})
tiles("Request count", INC_REQ, "short", "Number of LLM requests (count of gen_ai.server.request.duration).", 4, decimals=0)
tiles("Total token count", f'sum(increase({TOK}{{{F},gen_ai_token_type="total"}}[$__range]))', "short",
      "gen_ai.client.token.usage with gen_ai.token.type=total (input + output).", 8, decimals=0)
tiles("Cached token count", f'sum(increase({TOK}{{{F},gen_ai_token_type="cached_tokens"}}[$__range])) or vector(0)', "short",
      "gen_ai.token.type=cached_tokens. Stays 0 here: the mock provider returns no cache usage.", 12, decimals=0)
tiles("Error rate", f"({ERR_NUM} or vector(0)) / {INC_REQ}", "percentunit",
      "Requests whose duration metric carries an error.type, divided by all requests.", 16, decimals=1,
      thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 0.05}, {"color": "red", "value": 0.1}]})
tiles("Costs", f"sum(increase({COST}{{{F}}}[$__range]))", "currencyUSD",
      "kong.gen_ai.llm.cost. Computed from input_cost / output_cost ($ per 1M tokens) on each model target.", 20, decimals=3)
next_row(4)

# =========================================================================================================
# TOP CONSUMERS
# =========================================================================================================
row("Top consumers (selected range)")
top("Models", "gen_ai_request_model", 0, f"increase({REQ}{{{F}}}[$__range])", desc="Requests by model.")
top("Providers", "gen_ai_provider_name", 6, f"increase({REQ}{{{F}}}[$__range])", desc="Requests by provider.")
top("Users (consumers)", "kong_auth_consumer_name", 12, f"increase({REQ}{{{F}}}[$__range])",
    desc="Requests by AI Consumer. Needs enable_consumer_attribute on the OpenTelemetry policy.")
top("Users by tokens", "kong_auth_consumer_name", 18, f'increase({TOK}{{{F},gen_ai_token_type="total"}}[$__range])',
    desc="Total tokens by AI Consumer. (Konnect shows MCP Server here; see the MCP row below.)")
next_row(7)

# =========================================================================================================
# PERFORMANCE
# =========================================================================================================
row("Performance")
ts("Total requests", 0, 8, 8, [tgt(f"sum by (kong_gen_ai_request_mode) (rate({REQ}{{{F}}}[$__rate_interval]))", "{{kong_gen_ai_request_mode}}")],
   unit="reqps", stack=True, desc="Requests per second, split by oneshot vs stream.")
ts("LLM latency (p50 / p95 / p99)", 8, 8, 8,
   [tgt(pct(0.5), "p50", "A"), tgt(pct(0.95), "p95", "B"), tgt(pct(0.99), "p99", "C")], unit="s", desc="gen_ai.server.request.duration")
ts("Error rate", 16, 8, 8,
   [tgt(f'(sum(rate({REQ}{{{F},error_type!=""}}[$__rate_interval])) or vector(0)) / sum(rate({REQ}{{{F}}}[$__rate_interval]))', "error rate")],
   unit="percentunit", minv=0, desc="Share of requests with an error.type.")
next_row(8)
ts("Tokens per minute", 0, 8, 8,
   [tgt(f'sum by (gen_ai_token_type) (rate({TOK}{{{F},gen_ai_token_type=~"input|output"}}[$__rate_interval])) * 60', "{{gen_ai_token_type}}")],
   unit="short", stack=True, desc="Input and output tokens per minute (the 'total' series is left out to avoid double counting).")
ts("Time to first token (p50 / p95 / p99)", 8, 8, 8,
   [tgt(pct(0.5, metric="gen_ai_server_time_to_first_token_seconds"), "p50", "A"),
    tgt(pct(0.95, metric="gen_ai_server_time_to_first_token_seconds"), "p95", "B"),
    tgt(pct(0.99, metric="gen_ai_server_time_to_first_token_seconds"), "p99", "C")], unit="s",
   desc="gen_ai.server.time_to_first_token.")
ts("Time per output token (p50 / p95 / p99)", 16, 8, 8,
   [tgt(pct(0.5, metric="gen_ai_server_time_per_output_token_seconds"), "p50", "A"),
    tgt(pct(0.95, metric="gen_ai_server_time_per_output_token_seconds"), "p95", "B"),
    tgt(pct(0.99, metric="gen_ai_server_time_per_output_token_seconds"), "p99", "C")], unit="s",
   desc="gen_ai.server.time_per_output_token.")
next_row(8)

# =========================================================================================================
# COSTS
# =========================================================================================================
row("Costs")
ts("Total costs vs request count", 0, 12, 8,
   [tgt(f"sum(rate({COST}{{{F}}}[$__rate_interval])) * 60", "cost per minute ($)", "A"),
    tgt(f"sum(rate({REQ}{{{F}}}[$__rate_interval])) * 60", "requests per minute", "B")],
   desc="Cost (left axis, bars) against request volume (right axis, line).", fill=40,
   overrides=[{"matcher": {"id": "byName", "options": "cost per minute ($)"},
               "properties": [{"id": "unit", "value": "currencyUSD"}, {"id": "custom.drawStyle", "value": "bars"}, {"id": "custom.fillOpacity", "value": 60}]},
              {"matcher": {"id": "byName", "options": "requests per minute"},
               "properties": [{"id": "custom.axisPlacement", "value": "right"}, {"id": "unit", "value": "short"}, {"id": "custom.fillOpacity", "value": 0}, {"id": "custom.lineWidth", "value": 2}]}])
ts("Cost by model", 12, 12, 8, [tgt(f"sum by (gen_ai_request_model) (rate({COST}{{{F}}}[$__rate_interval])) * 60", "{{gen_ai_request_model}}")],
   unit="currencyUSD", stack=True, desc="Dollars per minute, stacked by model.")
next_row(8)

# =========================================================================================================
# MODELS
# =========================================================================================================
row("Models")
panel("table", "Success rate and usage by model", 0, 12, 8,
      [tgt(f"sum by (gen_ai_request_model) (increase({REQ}{{{F}}}[$__range]))", "", "A", instant=True, fmt="table"),
       tgt(f'1 - ((sum by (gen_ai_request_model) (increase({REQ}{{{F},error_type!=""}}[$__range]))) / sum by (gen_ai_request_model) (increase({REQ}{{{F}}}[$__range])) or sum by (gen_ai_request_model) (increase({REQ}{{{F}}}[$__range])) * 0)', "", "B", instant=True, fmt="table"),
       tgt(f'sum by (gen_ai_request_model) (increase({TOK}{{{F},gen_ai_token_type="total"}}[$__range]))', "", "C", instant=True, fmt="table")],
      desc="Per model: request count, success rate and total tokens in the selected range.",
      options={"showHeader": True, "cellHeight": "sm"},
      transformations=[{"id": "merge", "options": {}},
                       {"id": "organize", "options": {"excludeByName": {"Time": True},
                                                       "renameByName": {"gen_ai_request_model": "Model", "Value #A": "Requests", "Value #B": "Success rate", "Value #C": "Tokens"}}}],
      overrides=[{"matcher": {"id": "byName", "options": "Success rate"},
                  "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                                 {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}},
                                 {"id": "min", "value": 0}, {"id": "max", "value": 1},
                                 {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "orange", "value": 0.9}, {"color": "green", "value": 0.97}]}}]},
                 {"matcher": {"id": "byName", "options": "Requests"}, "properties": [{"id": "decimals", "value": 0}]},
                 {"matcher": {"id": "byName", "options": "Tokens"}, "properties": [{"id": "decimals", "value": 0}]}])
ts("Model usage by user", 12, 12, 8,
   [tgt(f"sum by (gen_ai_request_model, kong_auth_consumer_name) (rate({REQ}{{{F}}}[$__rate_interval]))", "{{kong_auth_consumer_name}} / {{gen_ai_request_model}}")],
   unit="reqps", stack=True, desc="Request rate for each consumer and model pair.")
next_row(8)
ts("Error rate per model", 0, 12, 8,
   [tgt(f'(sum by (gen_ai_request_model) (rate({REQ}{{{F},error_type!=""}}[$__rate_interval]))) / sum by (gen_ai_request_model) (rate({REQ}{{{F}}}[$__rate_interval]))', "{{gen_ai_request_model}}")],
   unit="percentunit", minv=0, desc="Share of requests with an error.type, per model. Series appear once a model has failed at least once.")
ts("Latency per model (p95)", 12, 12, 8, [tgt(pct(0.95, by="gen_ai_request_model"), "{{gen_ai_request_model}}")], unit="s",
   desc="p95 gen_ai.server.request.duration per model.")
next_row(8)

# =========================================================================================================
# MCP
# =========================================================================================================
row("MCP")
MCP_CALLS = 'mcp_server_operation_duration_seconds_count{mcp_method_name="tools/call"}'
MCP_BUCKET = 'mcp_server_operation_duration_seconds_bucket{mcp_method_name="tools/call"}'
top("Top MCP servers (tool calls)", "kong_service_name", 0, f"increase({MCP_CALLS}[$__range])", w=8,
    desc="tools/call count per MCP server (kong.service.name = the AI MCP Server name).")
ts("Method calls by tool", 8, 8, 7,
   [tgt(f"sum by (kong_service_name, gen_ai_tool_name) (rate({MCP_CALLS}[$__rate_interval]))", "{{kong_service_name}} / {{gen_ai_tool_name}}")],
   unit="reqps", stack=True, desc="mcp.server.operation.duration count for tools/call, by server and tool.")
ts("Failing method calls", 16, 8, 7,
   [tgt("sum by (kong_service_name, gen_ai_tool_name, error_type) (rate(kong_gen_ai_mcp_request_error_count_total[$__rate_interval]))", "{{kong_service_name}} / {{gen_ai_tool_name}} ({{error_type}})")],
   unit="reqps", desc="kong.gen_ai.mcp.request.error.count. The mock's run_ci_flaky tool fails about 30% of the time.")
next_row(7)
ts("MCP tool latency (p95)", 0, 12, 7,
   [tgt(f"histogram_quantile(0.95, sum by (le, gen_ai_tool_name)(rate({MCP_BUCKET}[$__rate_interval])))", "{{gen_ai_tool_name}}")],
   unit="s", desc="mcp.server.operation.duration for tools/call. slow_budget_report sleeps 1-3 s on purpose.")
ts("MCP response size (p95)", 12, 12, 7,
   [tgt("histogram_quantile(0.95, sum by (le, kong_service_name)(rate(kong_gen_ai_mcp_response_size_bytes_bucket[$__rate_interval])))", "{{kong_service_name}}")],
   unit="bytes", desc="kong.gen_ai.mcp.response.size")
next_row(7)

# =========================================================================================================
# GATEWAY HEALTH (not in Konnect AI Manager)
# =========================================================================================================
row("Gateway health (data plane)")
ts("HTTP responses by status code", 0, 8, 8,
   [tgt("sum by (http_response_status_code) (rate(http_server_request_count_total[$__rate_interval]))", "{{http_response_status_code}}")],
   unit="reqps", stack=True, desc="http.server.request.count by status. 200 = ok, 401 = bad key, 429/529 = provider errors passed back.")
ts("Kong latency (p95): total / upstream / internal", 8, 8, 8,
   [tgt('histogram_quantile(0.95, sum by (le)(rate(kong_latency_total_seconds_bucket[$__rate_interval])))', "total", "A"),
    tgt('histogram_quantile(0.95, sum by (le)(rate(kong_latency_upstream_seconds_bucket[$__rate_interval])))', "upstream (LLM)", "B"),
    tgt('histogram_quantile(0.95, sum by (le)(rate(kong_latency_internal_seconds_bucket[$__rate_interval])))', "internal (Kong)", "C")],
   unit="s", desc="Gateway overhead is 'internal'; the LLM provider is 'upstream'.")
panel("stat", "Control plane connection", 16, 4, 4,
      [tgt("min(kong_cp_connection_status_ratio)", "", "A", instant=True)], unit="percentunit",
      desc="kong.cp.connection.status: 1 = data plane connected to Konnect.",
      thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
      options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "background", "graphMode": "none", "textMode": "value"})
panel("stat", "DP certificate expires in", 20, 4, 4,
      [tgt("min(kong_dp_cluster_cert_expiry_seconds) - time()", "", "A", instant=True)], unit="s",
      desc="kong.dp.cluster.cert.expiry is an absolute timestamp; the panel subtracts now to show the time left on the mTLS certificate to Konnect.",
      thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "orange", "value": 1209600}, {"color": "green", "value": 2592000}]},
      options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value", "graphMode": "none", "textMode": "value"})
next_row(4)
ts("Request / response size (avg)", 16, 8, 4,
   [tgt("sum(rate(http_server_request_size_bytes_sum[$__rate_interval])) / sum(rate(http_server_request_size_bytes_count[$__rate_interval]))", "request", "A"),
    tgt("sum(rate(http_server_response_size_bytes_sum[$__rate_interval])) / sum(rate(http_server_response_size_bytes_count[$__rate_interval]))", "response", "B")],
   unit="bytes", desc="Needs enable_bandwidth_metrics.")
next_row(4)

# =========================================================================================================
# TRACES & LOGS (not in Konnect AI Manager)
# =========================================================================================================
row("Traces and logs")
panel("table", "Recent LLM traces (Tempo)", 0, 12, 10,
      [{"datasource": TEMPO, "refId": "A", "queryType": "traceql", "limit": 20, "tableType": "traces",
        "query": '{ resource.service.name = "$service_name" && span.gen_ai.request.model =~ "$model" }'}],
      ds=TEMPO, desc="Click a trace ID to open the waterfall: a 'kong' request span with a 'chat <model>' child carrying the gen_ai.* attributes.",
      options={"showHeader": True, "cellHeight": "sm"})
panel("logs", "Gateway access logs, errors only (Loki)", 12, 12, 10,
      [tgt('{service_name="$service_name"} | log_type="access" | http_response_status_code=~"4..|5.."', "", "A", ds=LOKI)],
      ds=LOKI, desc="OTLP access logs from the policy's access_logs endpoint. In 2.3 they are emitted for responses Kong itself produces (for example 401 from a bad key), not for requests proxied to the LLM.",
      options={"showTime": True, "wrapLogMessage": False, "enableLogDetails": True, "sortOrder": "Descending", "dedupStrategy": "none"})
next_row(10)
panel("timeseries", "Log volume by type (Loki)", 0, 12, 6,
      [tgt('sum by (log_type) (count_over_time({service_name="$service_name"}[$__interval]))', "{{log_type}}", ds=LOKI)],
      ds=LOKI, unit="short", desc="Runtime (error log) and access log records per interval.",
      custom={"drawStyle": "bars", "fillOpacity": 60, "stacking": {"mode": "normal", "group": "A"}, "lineWidth": 1},
      options={"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}})
panel("logs", "Gateway runtime logs (Loki)", 12, 12, 6,
      [tgt('{service_name="$service_name"} | log_type="error"', "", "A", ds=LOKI)],
      ds=LOKI, desc="Kong error/runtime log, exported through logs_endpoint. Needs the data plane log level info (KONG_LOG_LEVEL); at the default notice a healthy gateway writes almost none.",
      options={"showTime": True, "wrapLogMessage": False, "sortOrder": "Descending"})
next_row(6)


def dsvar(name, label, kind):
    return {"name": name, "label": label, "type": "datasource", "query": kind, "refresh": 1, "hide": 0,
            "multi": False, "includeAll": False, "current": {}, "options": []}


def tvar(name, label, metric, lbl):
    return {"name": name, "label": label, "type": "query", "datasource": PROM, "multi": True, "includeAll": True,
            "allValue": ".*", "current": {"selected": True, "text": "All", "value": "$__all"}, "refresh": 2, "sort": 1,
            "query": {"query": f"label_values({metric}, {lbl})", "refId": f"v-{name}"}, "definition": f"label_values({metric}, {lbl})"}


dash = {
    "uid": "kong-ai-gateway-overview",
    "title": "Kong AI Gateway: Overview",
    "description": "Modelled on the Konnect AI Manager overview page. Needs the AI Gateway 2.x OpenTelemetry policy exporting metrics (with enable_ai_metrics, enable_latency_metrics, enable_request_metrics, enable_consumer_attribute) to a Prometheus-compatible store; the Traces and logs row also needs Tempo and Loki.",
    "tags": ["kong", "ai-gateway", "opentelemetry"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": True, "graphTooltip": 1,
    "refresh": "10s", "time": {"from": "now-30m", "to": "now"},
    "templating": {"list": [
        dsvar("ds_prometheus", "Prometheus", "prometheus"),
        dsvar("ds_loki", "Loki", "loki"),
        dsvar("ds_tempo", "Tempo", "tempo"),
        {"name": "service_name", "label": "OTel service.name", "type": "textbox", "query": "kong-ai-gateway",
         "current": {"text": "kong-ai-gateway", "value": "kong-ai-gateway"}, "options": [{"selected": True, "text": "kong-ai-gateway", "value": "kong-ai-gateway"}],
         "description": "Value of resource_attributes.service.name set on the OpenTelemetry policy. Used by the Loki and Tempo panels."},
        tvar("provider", "Providers", TOK, "gen_ai_provider_name"),
        tvar("model", "AI Gateway models", TOK, "gen_ai_request_model"),
        tvar("consumer", "Consumers", TOK, "kong_auth_consumer_name"),
    ]},
    "links": [{"title": "Konnect (AI Manager > Overview)", "type": "link", "url": "https://cloud.konghq.com/", "targetBlank": True, "icon": "external link"}],
    "annotations": {"list": []},
    "panels": panels,
}
out = pathlib.Path(__file__).parent / "dashboards" / "kong-ai-gateway.json"
out.write_text(json.dumps(dash, indent=1))
print(f"wrote {out} ({len(panels)} top-level panels)")
