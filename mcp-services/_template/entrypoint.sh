#!/bin/sh
# 先自注册（失败不阻塞），再起 MCP 服务。
set -e
python /app/register.py || true
exec python /app/src/server.py
