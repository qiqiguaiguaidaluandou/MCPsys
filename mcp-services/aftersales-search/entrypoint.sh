#!/bin/sh
# 先自注册（失败不阻塞），再起 MCP 服务（pyproject 暴露的 console script: mcpserver）。
set -e
python /app/register.py || true
exec mcpserver
