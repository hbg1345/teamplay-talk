"""카카오 토큰 저장/조회 (users 테이블의 kakao_* 컬럼).

신원(kakao_id)은 친구의 storage.create_room/join_room이 이미 users에 넣는다.
이 모듈은 거기에 **알림용 토큰**을 얹고, 방 멤버의 토큰을 모아 조회한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from .crypto import decrypt_row_tokens, encrypt_token
from .db import conn


def set_kakao_token(
    kakao_id: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None = None,
) -> None:
    """이미 존재하는 user(kakao_id)에 카카오 토큰을 저장/갱신한다."""
    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    # 저장 직전에 암호화한다(키 미설정이면 평문 통과). refresh_token이 None이면
    # encrypt_token도 None을 반환해 아래 COALESCE가 기존 값을 보존한다.
    enc_access = encrypt_token(access_token)
    enc_refresh = encrypt_token(refresh_token)
    with conn() as c:
        with c.cursor() as cur:
            # refresh_token이 None이면 기존 값을 보존한다(헤더-브로커 토큰엔
            # refresh_token이 없을 수 있어, 링크 로그인 때 받은 걸 지우지 않도록).
            cur.execute(
                "UPDATE users SET kakao_access_token = %s, "
                "kakao_refresh_token = COALESCE(%s, kakao_refresh_token), "
                "kakao_token_expires_at = COALESCE(%s, kakao_token_expires_at) "
                "WHERE kakao_id = %s",
                (enc_access, enc_refresh, expires_at, kakao_id),
            )
        c.commit()


def list_members_with_tokens(room_id: int) -> list[dict[str, Any]]:
    """방 멤버 중 카카오 토큰을 가진 사람들(알림 대상)을 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT u.id, u.kakao_id, u.nickname, u.kakao_access_token, u.kakao_refresh_token "
                "FROM room_members rm "
                "JOIN rooms r ON r.id = rm.room_id "
                "JOIN users u ON u.id = rm.user_id "
                "WHERE rm.room_id = %s AND r.status = 'active' "
                "AND u.kakao_access_token IS NOT NULL "
                "ORDER BY rm.joined_at",
                (room_id,),
            )
            return [decrypt_row_tokens(r) for r in cur.fetchall()]


async def send_with_refresh(
    member: dict[str, Any],
    message: str,
    link_url: str = "https://playmcp.kakao.com",
) -> int:
    """member(kakao_access_token/refresh/kakao_id)에게 '나와의 채팅' 발송.

    access token 만료(401)면 refresh 후 1회 재시도. HTTP status 반환(200=성공).
    """
    from . import kakao
    from .config import settings

    status, _ = await kakao.send_to_me(member["kakao_access_token"], message, link_url=link_url)
    if status == 401 and member.get("kakao_refresh_token"):
        refreshed = await kakao.refresh_access_token(
            member["kakao_refresh_token"], settings.kakao_rest_api_key, settings.kakao_client_secret
        )
        if "access_token" in refreshed:
            set_kakao_token(
                member["kakao_id"],
                refreshed["access_token"],
                refreshed.get("refresh_token") or member["kakao_refresh_token"],
                refreshed.get("expires_in"),
            )
            status, _ = await kakao.send_to_me(refreshed["access_token"], message, link_url=link_url)
    return status


async def send_feed_with_refresh(
    member: dict[str, Any],
    *,
    title: str,
    description: str,
    link_url: str,
    button_title: str = "열기",
    items: list[tuple[str, str]] | None = None,
    fallback_text: str | None = None,
    reminder: dict[str, Any] | None = None,
) -> int:
    """member에게 카카오 feed 템플릿을 보내고 만료 토큰이면 갱신 후 1회 재시도."""
    from . import kakao
    from .config import settings

    status, _ = await kakao.send_feed_to_me(
        member["kakao_access_token"],
        title,
        description,
        link_url,
        button_title=button_title,
        items=items,
        fallback_text=fallback_text,
    )
    if status == 401 and member.get("kakao_refresh_token"):
        refreshed = await kakao.refresh_access_token(
            member["kakao_refresh_token"], settings.kakao_rest_api_key, settings.kakao_client_secret
        )
        if "access_token" in refreshed:
            set_kakao_token(
                member["kakao_id"],
                refreshed["access_token"],
                refreshed.get("refresh_token") or member["kakao_refresh_token"],
                refreshed.get("expires_in"),
            )
            status, _ = await kakao.send_feed_to_me(
                refreshed["access_token"],
                title,
                description,
                link_url,
                button_title=button_title,
                items=items,
                fallback_text=fallback_text,
            )
    if status == 200 and reminder:  # opt-in: reminder 준 발송(폼/투표/체크인)만 할 일 생성.
        try:  # 공지·다이제스트·역할통보는 reminder를 안 주므로 할 일 X (캘린더/todo 쪽에서 이미 생김)
            from . import task_sync
            await task_sync.pend_from_message(member, title=title, reminder=reminder)
        except Exception:
            pass
    return status
