"""카카오 토큰 엔드포인트 프록시.

PlayMCP가 OAuth 토큰 교환 시 client 자격증명을 **HTTP Basic**으로 보내면,
카카오 ``/token``(자격증명을 **body**로만 받음)이 거부한다. 구글은 Basic도
받아주기 때문에 같은 broker 경로에서 **구글은 되고 카카오만 실패**한다.

이 프록시를 PlayMCP의 **Token Endpoint URL**로 지정하면, Basic이든 body든 받아
**카카오가 받는 body 형식으로 변환**해 중계한다.

PlayMCP OAuth 폼 설정:
  Authorization Endpoint = https://kauth.kakao.com/oauth/authorize  (그대로)
  Token Endpoint         = https://<PUBLIC_BASE_URL>/kakao/token     (← 이 프록시)
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qs

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import kakao_store, storage
from .kakao import TOKEN_URL, get_user_info


async def _store_kakao_token_response(body: dict) -> None:
    """OAuth token 응답을 사용자별로 저장한다.

    PlayMCP는 토큰 교환 결과를 자기 쪽에 보관하지만, 팀원별 캘린더/알림을
    서버가 나중에 반복 실행하려면 우리 DB에도 refresh_token이 필요하다.
    저장 실패가 OAuth 자체 실패가 되면 안 되므로 호출부에서 예외를 삼킨다.
    """
    access_token = body.get("access_token")
    if not access_token:
        return
    kakao_id, nickname = await get_user_info(access_token)
    if not kakao_id or kakao_id == "unknown":
        return
    storage.upsert_user(kakao_id, nickname)
    kakao_store.set_kakao_token(
        kakao_id,
        access_token,
        body.get("refresh_token"),
        body.get("expires_in"),
    )


async def kakao_token_proxy(request: Request) -> JSONResponse:
    """PlayMCP의 토큰 요청을 카카오 /token에 body 방식으로 중계한다."""
    raw = (await request.body()).decode("utf-8")
    form = {k: v[0] for k, v in parse_qs(raw).items()}

    # client 자격증명이 HTTP Basic으로 왔으면 body로 옮긴다 (카카오는 body만 받음).
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            cid, _, csec = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            form.setdefault("client_id", cid)
            if csec:
                form.setdefault("client_secret", csec)
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TOKEN_URL, data=form)

    # 진단: 실패 시 카카오의 실제 에러를 로그에 남긴다.
    # (성공 응답엔 access_token이 들어있으니 본문은 찍지 않는다.)
    if resp.status_code != 200:
        print(f"[kakao_token_proxy] kakao /token -> {resp.status_code}: {resp.text}")

    try:
        body = resp.json()
    except Exception:
        return JSONResponse(
            {"error": "invalid_kakao_response", "raw": resp.text},
            status_code=resp.status_code,
        )
    if resp.status_code == 200:
        try:
            await _store_kakao_token_response(body)
        except Exception as exc:
            print(f"[kakao_token_proxy] token store failed: {type(exc).__name__}: {exc}")
    return JSONResponse(body, status_code=resp.status_code)


def register_kakao_token_proxy(mcp) -> None:
    """카카오 토큰 프록시 라우트(/kakao/token)를 등록한다."""
    mcp.custom_route("/kakao/token", methods=["POST"])(kakao_token_proxy)
