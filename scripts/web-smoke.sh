#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8088}"

echo "[web-smoke] /"
curl -sI "$BASE/" | grep -q "200 OK"

echo "[web-smoke] /favicon.svg"
curl -sI "$BASE/favicon.svg" | grep -q "200 OK"

echo "[web-smoke] SPA fallback"
curl -sI "$BASE/services/some-deep-route" | grep -q "200 OK"

echo "[web-smoke] grafana embed 200"
curl -sI "$BASE/grafana/d/mcpsys-overview/mcp-overview" | grep -q "200 OK"

echo "[web-smoke] backend api still works"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[web-smoke] OK"
