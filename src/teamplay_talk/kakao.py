"""카카오 OAuth + 나에게 보내기(메모) 클라이언트.

핵심: 카카오 로그인으로 사용자 토큰을 받고, **토큰 주인의 '나와의 채팅방'**으로
메시지를 보낸다. 팀 알림은 "각 멤버 토큰으로 self-push"를 반복하는 것뿐이다.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USER_ME_URL = "https://kapi.kakao.com/v2/user/me"
MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

DEFAULT_SCOPE = "talk_message,profile_nickname"


def build_authorize_url(
    rest_api_key: str,
    redirect_uri: str,
    scope: str = DEFAULT_SCOPE,
    state: str | None = None,
) -> str:
    """카카오 로그인 인가 요청 URL. state에 의도를 실어 콜백에서 활용한다."""
    params = {
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(
    code: str,
    rest_api_key: str,
    redirect_uri: str,
    client_secret: str | None = None,
) -> dict:
    """인가 코드를 access/refresh 토큰으로 교환. (실패 시 error 필드 포함 dict)"""
    data = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TOKEN_URL, data=data)
    return resp.json()


async def refresh_access_token(
    refresh_token: str,
    rest_api_key: str,
    client_secret: str | None = None,
) -> dict:
    """refresh_token으로 access_token을 갱신한다. (응답에 refresh_token이 올 수도 있음)"""
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TOKEN_URL, data=data)
    return resp.json()


async def get_user_info(access_token: str) -> tuple[str, str]:
    """토큰 주인의 (kakao_id, nickname) 조회."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(USER_ME_URL, headers={"Authorization": f"Bearer {access_token}"})
    data = resp.json()
    uid = str(data.get("id", "unknown"))
    nickname = ((data.get("kakao_account") or {}).get("profile") or {}).get("nickname") or "이름없음"
    return uid, nickname


async def send_to_me(
    access_token: str,
    text: str,
    link_url: str = "https://playmcp.kakao.com",
) -> tuple[int, str]:
    """토큰 주인의 '나와의 채팅방'으로 텍스트 메시지 발송. (status_code, body) 반환."""
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": link_url, "mobile_web_url": link_url},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            MEMO_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
        )
    return resp.status_code, resp.text
