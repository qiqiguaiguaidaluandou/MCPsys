import json
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from mcpsys_shared.models import CallStatus

from ..auth import AuthError, validate_api_key
from ..proxy import ProxyTimeout, forward
from ..resolver import ServiceNotFound
from ..settings import settings
from ..telemetry import CallLogEntry

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _truncate(b: bytes | None, limit: int) -> str | None:
    if b is None:
        return None
    if len(b) <= limit:
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return None
    head = b[:limit]
    return head.decode("utf-8", errors="replace") + f"\n...[truncated {len(b) - limit} bytes]"


def _extract_method_and_id(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    method = payload.get("method")
    if method == "tools/call":
        params = payload.get("params") or {}
        method = f"tools/call:{params.get('name')}" if isinstance(params, dict) else method
    rid = payload.get("id")
    return method, str(rid) if rid is not None else None


@router.post("/{slug}")
async def proxy_mcp(
    slug: str,
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
) -> Response:
    request_id = str(uuid.uuid4())
    body = await request.body()
    client_ip = request.client.host if request.client else None
    tool_label, jsonrpc_id = _extract_method_and_id(body)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    plaintext = authorization.split(None, 1)[1].strip()

    sf = request.app.state.session_factory
    redis = request.app.state.redis
    resolver = request.app.state.resolver
    http = request.app.state.http
    telemetry = request.app.state.telemetry

    # 1. authn
    try:
        resolved_key = await validate_api_key(
            plaintext,
            session_factory=sf,
            redis=redis,
            ttl_seconds=settings.api_key_cache_ttl_seconds,
        )
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    # 2. resolve
    try:
        svc = await resolver.resolve(slug)
    except ServiceNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service not found: {slug}") from e

    # 3. authz: MVP only checks key is active (already enforced in step 1)

    # 4. forward
    extra = {
        "x-request-id": request_id,
        "x-mcpsys-application": str(resolved_key.application_id or ""),
        "x-mcpsys-user": str(resolved_key.user_id or ""),
    }
    call_status = CallStatus.success
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    proxy_body: bytes = b""
    duration_ms = 0
    try:
        result = await forward(
            client=http,
            upstream_url=svc.endpoint_url,
            body=body,
            headers=dict(request.headers),
            extra_headers=extra,
        )
        http_status = result.status
        proxy_body = result.body
        duration_ms = result.duration_ms
        if result.status >= 500:
            call_status = CallStatus.error
            error_code = f"upstream_{result.status}"
        elif result.status >= 400:
            call_status = CallStatus.error
            error_code = f"client_{result.status}"
        response_obj = Response(
            content=result.body,
            status_code=result.status,
            headers={
                k: v
                for k, v in result.headers.items()
                if k.lower() not in {"content-length", "transfer-encoding", "connection"}
            },
            media_type=result.headers.get("content-type"),
        )
    except ProxyTimeout as e:
        call_status = CallStatus.timeout
        http_status = 504
        error_code = "timeout"
        error_message = str(e)
        response_obj = Response(
            content=json.dumps({"error": {"code": "timeout", "message": str(e)}}).encode(),
            status_code=504,
            media_type="application/json",
        )
    except Exception as e:
        call_status = CallStatus.error
        http_status = 502
        error_code = "proxy_error"
        error_message = str(e)
        response_obj = Response(
            content=json.dumps({"error": {"code": "proxy_error", "message": str(e)}}).encode(),
            status_code=502,
            media_type="application/json",
        )

    # 5. telemetry (fire and forget)
    entry = CallLogEntry(
        api_key_id=resolved_key.api_key_id,
        application_id=resolved_key.application_id,
        user_id=resolved_key.user_id,
        service_id=svc.service_id,
        service_version=None,
        tool_name=tool_label,
        request_id=jsonrpc_id or request_id,
        status=call_status,
        http_status=http_status,
        error_code=error_code,
        error_message=error_message,
        duration_ms=duration_ms,
        request_bytes=len(body),
        response_bytes=len(proxy_body),
        request_body=_truncate(body, settings.body_log_max_bytes),
        response_body=_truncate(proxy_body, settings.body_log_max_bytes),
        client_ip=client_ip,
    )
    await telemetry.enqueue(entry)

    response_obj.headers["x-request-id"] = request_id
    return response_obj
