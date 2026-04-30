# MCPsys

Internal MCP (Model Context Protocol) service management system.

- Spec: `docs/specs/2026-04-30-mcp-management-system-design.md`
- MVP plan: `docs/plans/2026-04-30-mcp-management-mvp-plan.md`

## Quick start

```bash
cp .env.example .env
# edit .env: set a strong JWT_SECRET (>= 32 chars). Use:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose build
docker compose up -d

# wait ~30s for healthchecks, then create the initial admin user
docker compose exec control-plane python scripts/seed_admin.py admin SuperSecret123

# run end-to-end smoke
./scripts/smoke.sh
```

Endpoints:

| URL | Purpose |
|---|---|
| `http://localhost/healthz` | Control-plane health |
| `http://localhost/gw/healthz` | Gateway health |
| `http://localhost/api/v1/...` | Management API (JWT) |
| `http://localhost/mcp/{slug}` | MCP traffic gateway (API Key) |
| `http://localhost/grafana/` | Monitoring dashboard |

## Development

```bash
# install workspace
uv sync

# run tests for a specific package
uv run --package control-plane pytest services/control_plane/tests
uv run --package gateway        pytest services/gateway/tests
uv run --package mcpsys-shared  pytest packages/mcpsys_shared/tests
```

## Architecture

See `docs/specs/2026-04-30-mcp-management-system-design.md` §2 for the architecture diagram.

## Operational notes

- **TLS termination**: The bundled nginx listens on HTTP :80 only. Production deployments are expected to terminate TLS at a corporate edge (or an additional reverse proxy) upstream of this nginx. Add `listen 443 ssl;` to `nginx/nginx.conf` if you want this nginx to do termination directly.
- **Scaling the gateway**: A single gateway replica is sufficient at MVP scale (≤100 QPS). Multi-replica scaling needs an nginx upstream block with a runtime DNS resolver (e.g. `resolver 127.0.0.11 valid=10s; set $upstream gateway:8080; proxy_pass http://$upstream;`) — deferred to v1.
- **Backups**: Postgres `pg_dump` is not yet automated; deploy a host-level cron or sidecar in production.
