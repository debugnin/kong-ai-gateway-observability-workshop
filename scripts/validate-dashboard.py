#!/usr/bin/env python3
"""Runs every panel query of the provisioned dashboard against Grafana's datasources and reports errors / empty panels.
Usage: python3 scripts/validate-dashboard.py [grafana_url]   (default http://localhost:3000, admin/admin)"""
import base64, json, re, sys, time, urllib.parse, urllib.request

G = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
AUTH = "Basic " + base64.b64encode(b"admin:admin").decode()


def get(path):
    r = urllib.request.Request(G + path, headers={"Authorization": AUTH})
    return json.load(urllib.request.urlopen(r, timeout=30))


def sub(e):
    for k, v in {"$provider": ".*", "$model": ".*", "$consumer": ".*", "$__range": "30m", "$__rate_interval": "1m", "$__interval": "1m"}.items():
        e = e.replace(k, v)
    return e


dash = get("/api/dashboards/uid/kong-ai-gateway-overview")["dashboard"]
flat = []
for p in dash["panels"]:
    flat.append(p)
    flat += p.get("panels", [])
bad = 0
now = int(time.time())
for p in flat:
    if p["type"] == "row":
        continue
    for t in p["targets"]:
        ds = t["datasource"]["type"]
        try:
            if ds == "prometheus":
                res = get(f"/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode({"query": sub(t["expr"])}))
                n = len(res["data"]["result"])
            elif ds == "loki":
                res = get("/api/datasources/proxy/uid/loki/loki/api/v1/query_range?" + urllib.parse.urlencode(
                    {"query": sub(t["expr"]), "start": (now - 1800) * 10**9, "end": now * 10**9, "limit": 5, "step": 60}))
                n = len(res["data"]["result"])
            elif ds == "tempo":
                res = get("/api/datasources/proxy/uid/tempo/api/search?" + urllib.parse.urlencode(
                    {"q": sub(t["query"]), "limit": 5, "start": now - 1800, "end": now}))
                n = len(res.get("traces", []))
            else:
                continue
            status = "ok   " if n else "EMPTY"
            if not n:
                bad += 1
        except Exception as e:  # query syntax errors come back as HTTP 400
            status, n = "ERROR", str(e)[:80]
            bad += 1
        print(f"{status} {p['title'][:44]:44} [{t['refId']}] {n}")
print(f"\n{bad} problem(s)")
sys.exit(1 if bad else 0)
