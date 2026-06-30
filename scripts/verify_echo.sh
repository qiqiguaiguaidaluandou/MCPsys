#!/usr/bin/env bash
# 阶段 1 端到端验证：echo MCP 服务经网关打通。
#
# 前置：
#   1) 主栈 + echo 已起：
#        docker compose -f compose.yaml -f compose.mcp.yaml up -d --build
#   2) 已建管理员（README §5）。非默认密码请先 export PASSWORD=...
#
# 用法：  ./scripts/verify_echo.sh
# 成功以 [verify] OK 结尾，证明：注册 → 授权 → 经网关调用 echo → 落 call_logs 全链路通。
set -euo pipefail

BASE="${BASE:-http://localhost:8088}"
USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-admin123}"
ENDPOINT="${ENDPOINT:-http://mcp-echo:8000/mcp}"   # echo 在 mcpsys 内网的地址

RUN_SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "[verify] healthz"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[verify] login"
TOKEN=$(curl -fsS -X POST "$BASE/api/v1/auth/login" \
    -H "content-type: application/x-www-form-urlencoded" \
    --data-urlencode "username=$USERNAME" --data-urlencode "password=$PASSWORD" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "[verify] register echo service (idempotent) → $ENDPOINT"
curl -fsS -X POST "$BASE/api/v1/services" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"slug\":\"echo\",\"display_name\":\"Echo 测试服务\",\"endpoint_url\":\"$ENDPOINT\"}" >/dev/null || true
SVC_ID=$(curl -fsS "$BASE/api/v1/services/echo" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "[verify]   echo service id: $SVC_ID"

echo "[verify] create application (idempotent)"
curl -fsS -X POST "$BASE/api/v1/applications" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"verify-echo-app"}' >/dev/null || true
APP_ID=$(curl -fsS "$BASE/api/v1/applications" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; apps=json.load(sys.stdin)['items']; print(next(a['id'] for a in apps if a['name']=='verify-echo-app'))")

echo "[verify] issue api key"
APIKEY=$(curl -fsS -X POST "$BASE/api/v1/api-keys" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"name\":\"verify-echo\",\"application_id\":$APP_ID}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['plaintext'])")

echo "[verify] authorize: set app service_ids=[$SVC_ID]"
curl -fsS -X PATCH "$BASE/api/v1/applications/$APP_ID" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"service_ids\":[$SVC_ID]}" >/dev/null

echo "[verify] call echo through gateway (MCP initialize)"
BODY_FILE=$(mktemp)
HTTP=$(curl -s -o "$BODY_FILE" -w "%{http_code}" -X POST "$BASE/mcp/echo" \
    -H "Authorization: Bearer $APIKEY" \
    -H "content-type: application/json" \
    -H "accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify","version":"0"}}}')
echo "[verify]   gateway returned HTTP $HTTP"
case "$HTTP" in
    401|403|404|429)
        echo "[verify] FAIL: 网关在转发前就拒了（鉴权/授权/解析/限流）。响应："; cat "$BODY_FILE"; rm -f "$BODY_FILE"; exit 1;;
    502|504)
        echo "[verify] FAIL: 网关连不上 echo（容器没起？内网地址不对？）。响应："; cat "$BODY_FILE"; rm -f "$BODY_FILE"; exit 1;;
    200)
        echo "[verify]   upstream 200 OK（echo 正常响应 initialize）";;
    *)
        echo "[verify] 注意：upstream 返回 $HTTP，链路已通但 echo 响应非 200，body："; head -c 400 "$BODY_FILE"; echo;;
esac
rm -f "$BODY_FILE"

echo "[verify] assert a call_logs row was written for echo since run-start"
CNT=$(curl -fsS "$BASE/api/v1/call-logs?service_id=$SVC_ID&from=$RUN_SINCE&limit=1" \
    -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
test "$CNT" -ge 1 || { echo "[verify] FAIL: 未写入 echo 的调用日志（自 $RUN_SINCE 起 0 条）"; exit 1; }
echo "[verify]   call_logs for echo since run-start: total=$CNT"

echo "[verify] OK"
