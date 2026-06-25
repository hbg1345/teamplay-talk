"""카카오 푸쉬 스파이크 (데모 하네스) — 여러 명 로그인 + "팀 전체 알림" 검증.

실제 카카오 로직은 ``src/teamplay_talk/kakao.py`` 모듈에 있고, 여기선 그걸 쓰는
HTTP 데모만 한다. DB·팀 바인딩 없이 토큰은 메모리에 user_id 별로 저장.

흐름:
  1. (공개 URL로) 각자 접속 → "카카오 로그인" → 동의(talk_message)
  2. 콜백에서 토큰 교환 + 내 정보 조회 → user_id 별 저장 → 환영 메시지 발송
  3. 누구든 /notify-all 호출 → 저장된 전원에게 push  ← 팀 알림(남이 트리거)
  4. 각자 카톡 "나와의 채팅방"에 도착하면 성공

실행:  uv run python scripts/kakao_push_spike.py
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from teamplay_talk import kakao


def load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env()

REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/callback")

# 스파이크용 메모리 저장소: user_id -> {access_token, refresh_token, nickname, scope}
MEMBERS: dict[str, dict] = {}


async def index(request: Request) -> HTMLResponse:
    if MEMBERS:
        rows = "".join(f"<li>{m['nickname']}</li>" for m in MEMBERS.values())
        members_html = f"<ul>{rows}</ul>"
    else:
        members_html = "<p>(아직 아무도 로그인 안 함)</p>"
    return HTMLResponse(
        f"""<html><body style="font-family:sans-serif;max-width:640px;margin:40px auto">
        <h2>카카오 팀 푸쉬 스파이크</h2>
        <h3>로그인한 팀원 ({len(MEMBERS)}명)</h3>
        {members_html}
        <p><a href="/login"><b>① 카카오 로그인 + 동의</b></a> (각자 한 번씩)</p>
        <p><a href="/notify-all"><b>② 팀 전체에게 알림 쏘기</b></a></p>
        </body></html>"""
    )


async def login(request: Request) -> RedirectResponse:
    return RedirectResponse(kakao.build_authorize_url(REST_API_KEY, REDIRECT_URI))


async def callback(request: Request) -> HTMLResponse:
    if error := request.query_params.get("error"):
        desc = request.query_params.get("error_description", "")
        return HTMLResponse(f"<h3>로그인 에러: {error}</h3><p>{desc}</p><a href='/'>홈</a>")

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h3>code 없음</h3><a href='/'>홈</a>")

    tokens = await kakao.exchange_code_for_token(code, REST_API_KEY, REDIRECT_URI, CLIENT_SECRET)
    if "access_token" not in tokens:
        return HTMLResponse(f"<h3>토큰 교환 실패</h3><pre>{tokens}</pre><a href='/'>홈</a>")

    uid, nickname = await kakao.get_user_info(tokens["access_token"])
    MEMBERS[uid] = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "nickname": nickname,
        "scope": tokens.get("scope", ""),
    }

    status, body = await kakao.send_to_me(
        tokens["access_token"], f"🎉 {nickname}님 연결 완료! 이제 팀 알림을 받습니다."
    )
    ok = "✅ 환영 메시지 발송 성공! 카톡 확인하세요." if status == 200 else f"❌ 발송 실패 ({status})"
    return HTMLResponse(
        f"""<html><body style="font-family:sans-serif;max-width:640px;margin:40px auto">
        <h2>{ok}</h2>
        <p>{nickname}님 로그인됨. 현재 팀원 {len(MEMBERS)}명.</p>
        <p>동의 scope: <code>{tokens.get('scope', '')}</code></p>
        <pre>{body}</pre>
        <a href='/'>홈으로</a>
        </body></html>"""
    )


async def notify_all(request: Request) -> JSONResponse:
    if not MEMBERS:
        return JSONResponse({"error": "로그인한 팀원이 없습니다"}, status_code=400)
    results = {}
    for info in MEMBERS.values():
        status, _ = await kakao.send_to_me(
            info["access_token"],
            f"📢 팀 알림 테스트 — {info['nickname']}님, 이 메시지는 다른 사람이 트리거했어요!",
        )
        results[info["nickname"]] = "성공" if status == 200 else f"실패({status})"
    return JSONResponse({"발송결과": results})


app = Starlette(
    routes=[
        Route("/", index),
        Route("/login", login),
        Route("/auth/kakao/callback", callback),
        Route("/notify-all", notify_all),
    ]
)


if __name__ == "__main__":
    import uvicorn

    print(f"REDIRECT_URI: {REDIRECT_URI}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
