"""구글 OAuth 클라이언트 — Drive 토큰 수집용.

우리 OAuth 인가 서버가 카카오 인증 직후 사용자를 구글로 한 번 더 보내,
``drive.file`` 토큰을 받아 저장한다(체인). kakao.py 와 같은 형태.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# 앱이 만든 파일만 접근(최소 권한). 식별은 카카오로 이미 했으므로 Drive만.
DEFAULT_SCOPE = "https://www.googleapis.com/auth/drive.file"


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    scope: str = DEFAULT_SCOPE,
    state: str | None = None,
) -> str:
    """구글 인가 요청 URL. refresh_token을 받기 위해 offline+consent 지정."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """인가 코드를 access/refresh 토큰으로 교환. (실패 시 error 필드 포함 dict)"""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TOKEN_URL, data=data)
    return resp.json()
