"""teamplay-talk MCP 서버 — P0 스캐폴드.

PlayMCP 공모전용 팀플(팀 프로젝트) 협업 MCP 서버.

P0 목표:
- ``tools/list`` 를 **무인증**으로 노출 (PlayMCP 등록 전제 조건)
- ``/health`` 헬스체크 엔드포인트
- 더미 도구 1개(``teamplay_ping``)

실행: ``teamplay-talk`` (또는 ``python -m teamplay_talk.server``)
MCP 엔드포인트: ``http://<host>:<port>/mcp/``
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .config import settings
from .dashboard_web import register_dashboard_routes
from .forms_web import register_form_routes
from .kakao_token_proxy import register_kakao_token_proxy
from .tools import register_all
from .triggers import start_scheduler

mcp = FastMCP(
    name="teamplay-talk",
    instructions=(
        "팀플(팀 프로젝트) 협업 MCP — 팀 방·투표/폼·역할분배·일정조율·카카오 알림.\n"
        "원칙: ① 팀원은 이미 방에 있으니 rooms로 조회하고 사용자에게 이름 묻지 마. "
        "② 투표 선택지·역할·회의 후보시간은 프로젝트 맥락 보고 네가 직접 생성(사용자에게 떠넘기지 마). "
        "③ 역할분배: assign_roles → [팀장 확인] → send_form → finalize_roles → [확인] → set_roles. "
        "④ 정하기: **회의 일정**은 schedule_meeting()(기본 오늘부터 14일×시간 O/X 그리드)으로 "
        "생성 → [팀장 확인] → send_form → get_poll_results의 **best_slots**"
        "(X 0명 중 O 최다, 동점 전부) 공지. "
        "**그 외 후보가 뻔하면** create_poll 복수선택, **막연하면**(주제·장소 등) gather_opinions "
        "(2단계: 자유의견→항목화→본투표). 후보는 AI/멤버가 생성(사용자에 떠넘기지 마). "
        "약속장소는 먼저 gather_opinions로 출발 위치/선호 장소를 모으고, 같은 역·상권·동네는 "
        "AI가 정규화해 묶어라. 카카오맵 MCP가 사용 가능하면 위치 검색으로 중간 후보/주변 장소를 "
        "추가하고, 없으면 팀원이 제출한 후보만 정규화해 create_poll로 본투표를 만든다. "
        "⑤ 폼 배포는 notify_room이 아니라 send_form. "
        "⑥ 방의 지금까지 결과를 한눈에 보려면 room_dashboard."
    ),
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> PlainTextResponse:
    """배포 헬스체크용 엔드포인트."""
    return PlainTextResponse("ok")


# 도메인별 도구 등록
register_all(mcp)

# 네이티브 폼 웹 페이지(/form/<id>) 등록
register_form_routes(mcp)

# 방별 SurveyJS 결과 대시보드(/dashboard/rooms/<id>) 등록
register_dashboard_routes(mcp)

# 카카오 토큰 프록시(/kakao/token) — PlayMCP의 Basic 인증을 카카오용 body로 변환
register_kakao_token_proxy(mcp)


def main() -> None:
    start_scheduler()  # 폼 마감 감지 + 드라이버 nudge (백그라운드)
    mcp.run(transport="http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
