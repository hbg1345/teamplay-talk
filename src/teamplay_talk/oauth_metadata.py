"""OAuth discovery 메타데이터 엔드포인트.

내부 PlayMCP는 OAuth 설정을 폼에 수동 입력하지만, 외부 AI 클라이언트
(Claude/ChatGPT 등)는 표준 OAuth **자동 발견(discovery)**에 의존한다:
- RFC 9728: ``/.well-known/oauth-protected-resource``
- RFC 8414: ``/.well-known/oauth-authorization-server``

우리의 기존 설정(authorization=카카오, token=우리 프록시)을 그대로 **광고**만
한다. 작동 중인 내부 흐름·resolve_caller·토큰 프록시는 건드리지 않는다.

주의:
- issuer/resource는 요청이 도달한 origin(KC 또는 DO) 기준으로 동적 생성한다
  (프록시 뒤라 x-forwarded-* 우선). RFC 8414상 issuer는 메타데이터가 서빙된
  URL과 일치해야 하므로 하드코딩하지 않는다.
- token_endpoint는 **DO(Caddy)** 프록시로 고정한다. KC(Envoy)는 외부 OAuth
  토큰교환을 막으므로(경험), 외부 클라는 DO 프록시로 교환해야 한다.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

_KAKAO_AUTHORIZE = "https://kauth.kakao.com/oauth/authorize"
# 외부 OAuth 토큰교환은 DO 프록시로 — KC Envoy가 외부 클라 토큰교환을 막음.
_TOKEN_ENDPOINT = "https://teamplay-talk.tech/kakao/token"
_SCOPES = ["talk_message", "profile_nickname", "talk_calendar", "talk_calendar_task"]


def _origin(request: Request) -> str:
    """요청이 도달한 공개 origin (프록시 뒤 고려)."""
    headers = request.headers
    host = headers.get("x-forwarded-host") or headers.get("host") or request.url.netloc
    proto = headers.get("x-forwarded-proto") or ("https" if request.url.scheme == "https" else "http")
    return f"{proto}://{host}"


async def _protected_resource(request: Request) -> JSONResponse:
    base = _origin(request)
    return JSONResponse(
        {
            "resource": f"{base}/mcp",
            "authorization_servers": [base],
            "scopes_supported": _SCOPES,
        }
    )


async def _authorization_server(request: Request) -> JSONResponse:
    base = _origin(request)
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": _KAKAO_AUTHORIZE,
            "token_endpoint": _TOKEN_ENDPOINT,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": _SCOPES,
        }
    )


def register_oauth_metadata(mcp) -> None:
    """OAuth discovery 라우트(.well-known)를 등록한다."""
    mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(_protected_resource)
    # MCP 클라이언트는 path-scoped variant(/.well-known/oauth-protected-resource/mcp)도 조회한다.
    mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])(_protected_resource)
    mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])(_authorization_server)
