"""OAuth 보호 리소스 메타데이터 (RFC 9728).

MCP 리소스 서버(이 서버의 ``/mcp``)가 "나를 보호하는 인증서버는 누구인가"를
광고한다. 외부 AI 클라이언트(Claude/ChatGPT 등)는 이 메타데이터로 우리
**자체 인증서버**(oauth_server.py, DO)를 발견해 OAuth를 시작한다.

- ``resource``: 이 요청이 도달한 origin 기준(KC 또는 DO)의 ``/mcp``.
- ``authorization_servers``: **항상 우리 AS(oauth_as_base_url=DO)**. KC로 리소스
  메타데이터가 서빙돼도 인증은 DO에서 하도록 고정한다(KC Envoy가 외부 토큰교환을
  막으므로). 인증서버 메타데이터(RFC 8414)는 oauth_server.py가 서빙한다.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings

_SCOPES = ["talk_message", "profile_nickname", "talk_calendar", "talk_calendar_task"]


def _origin(request: Request) -> str:
    """요청이 도달한 공개 origin (프록시 뒤 x-forwarded-* 우선)."""
    headers = request.headers
    host = headers.get("x-forwarded-host") or headers.get("host") or request.url.netloc
    proto = headers.get("x-forwarded-proto") or (
        "https" if request.url.scheme == "https" else "http"
    )
    return f"{proto}://{host}"


async def _protected_resource(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": f"{_origin(request)}/mcp",
            "authorization_servers": [settings.oauth_as_base_url.rstrip("/")],
            "scopes_supported": _SCOPES,
        }
    )


def register_oauth_metadata(mcp) -> None:
    """OAuth 보호 리소스 메타데이터(.well-known) 라우트를 등록한다."""
    mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(
        _protected_resource
    )
    # MCP 클라이언트는 path-scoped variant(/.well-known/oauth-protected-resource/mcp)도 조회한다.
    mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])(
        _protected_resource
    )
