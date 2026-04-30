# MCPsys

Internal MCP (Model Context Protocol) service management system.

- Spec: `docs/specs/2026-04-30-mcp-management-system-design.md`
- MVP plan: `docs/plans/2026-04-30-mcp-management-mvp-plan.md`

## Quick start

```bash
cp .env.example .env
# edit .env: set strong JWT_SECRET and CONFIG_FERNET_KEY (generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

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
