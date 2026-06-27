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
        "도구 호출 뒤 사용자에게 답할 때는 항상 '현재 상태'와 '다음에 할 수 있는 선택지 2~4개'를 짧게 말하라. "
        "예: 공지 발송, 결과 조회, 본투표 생성, 로드맵/todo 반영, 캘린더 등록. "
        "도구 응답의 next/suggested_next_actions/chat_response_hint를 우선 반영하라. "
        "폼/투표/역할/일정 도구를 만들기만 한 상태(sent=false)에서는 절대 '보냈다/요청했다'고 말하지 말고 "
        "반드시 send_form 결과의 sent_to/count를 확인한 뒤 발송 성공 여부를 말해라. "
        "notify_room도 sent_to가 비어 있으면 공지 성공이라고 말하지 마라. "
        "③ 역할분배는 일반 create_poll이 아니라 assign_roles 전용 흐름: "
        "assign_roles → [팀장 확인] → send_form → finalize_roles → [확인] → set_roles. "
        "finalize_roles는 계산만 하고 저장하지 않는다. set_roles 전에는 역할이 확정/저장됐다고 말하지 마라. "
        "finalize_roles 뒤 사용자가 할일/로드맵 다음 단계를 물으면, 먼저 set_roles로 확정 저장이 필요한지 확인하라. "
        "핵심 구현처럼 여러 명이 필요한 역할은 roles[].slots를 2 이상으로 잡아 워크포스를 배분하라. "
        "로드맵 이후 역할분배를 할 때는 로드맵 태스크명(대회 주제 선정/프로토타입 개발/최종 제출 등)을 "
        "역할로 쓰지 말고 기획·PM, MCP 서버·도구 구현, 카카오 API·OAuth 연동, 테스트·QA, 문서·데모·발표처럼 "
        "여러 태스크를 책임지는 역량/워크스트림 역할로 바꿔 assign_roles에 넣어라. "
        "사용자가 '팀원별로 나눠줘/역할별 todo를 팀원에게 배정해줘'라고 하면 daily_task_digest를 먼저 호출하지 마라. "
        "먼저 set_roles가 완료됐는지 확인하고, decompose_roadmap 또는 역할명 todo 동기화 후 member_tasks(member='all')로 실제 배정 결과를 보여줘라. "
        "daily_task_digest는 배정 도구가 아니라 배정 완료된 개인 todo를 카카오로 공지하는 도구다. "
        "④ 정하기: **회의 일정**은 schedule_meeting()(기본 오늘부터 14일×시간 O/X 그리드)으로 "
        "생성 → [팀장 확인] → send_form → get_poll_results의 **best_slots**"
        "(X 0명 중 O 최다, 동점 전부) 공지. 확정된 회의를 방 멤버 전원 톡캘린더에 넣으려면 "
        "calendar_create_room_event를 사용한다(각 멤버 talk_calendar 인증 필요). "
        "**그 외 후보가 뻔하면** create_poll 복수선택, **막연한 주제는** gather_opinions "
        "(2단계: 자유의견→항목화→본투표). get_poll_results의 outcome/suggested_next_actions를 "
        "보고 공지·로드맵·캘린더 후속 액션으로 이어라. 후보는 AI/멤버가 생성(사용자에 떠넘기지 마). "
        "약속장소는 gather_locations를 우선 사용한다. 위치 1~5칸 응답을 같은 역·상권·동네로 정규화해 묶어라. "
        "두 출발지 사이의 중간역/이동시간을 자동 추천한다고 약속하지 마라. "
        "현재 대화의 사용 가능한 도구 목록에 카카오맵/지도 MCP 도구가 보이면 장소명·역명·주소 확인과 중복 후보 정규화에만 보조적으로 사용하라. "
        "카카오맵/지도 도구가 보이지 않으면 '카카오맵 MCP가 있으면 장소명/주소 확인이 더 정확해지고, 지금은 제출된 텍스트 기준으로 후보를 정리해 투표할 수 있다'고 안내한 뒤 제출 후보만 정규화해 create_poll로 본투표를 만든다. "
        "⑤ 폼 배포는 notify_room이 아니라 send_form. "
        "⑥ 로드맵/할일은 한 번에 끝내지 말고 계속 루프로 관리한다: "
        "gather_task_opinions(scope='roadmap'|'todo'|'blockers'|'scope') → send_form → get_poll_results → "
        "AI가 중복 표현을 합쳐 태스크/담당/마감/리스크 후보로 정규화 → decompose_roadmap 또는 add_task/update_task 또는 create_poll 우선순위 투표 → "
        "member_tasks로 개인별 할일 확인 → daily_task_digest/캘린더. "
        "build_roadmap은 큰 단계(milestone)용이고 개인 실행 todo가 아니다. 사용자가 '각자 todo 초안', '조원별 할일'을 물으면 "
        "로드맵 milestone을 decompose_roadmap으로 1~2일짜리 실행 todo 여러 개로 분해한 뒤 member_tasks를 조회하라. "
        "팀원 의견 원문 하나를 add_task 한 줄로 저장하지 말고, 필요한 하위 작업으로 쪼개라. "
        "개인별 할일을 말할 때는 기억으로 말하지 말고 view_roadmap/member_tasks가 반환한 DB 태스크를 기준으로 말해라. "
        "⑦ 방의 지금까지 결과와 확정 회의시간/장소/역할은 room_dashboard 또는 rooms의 latest_decisions를 확인해라. "
        "기존 로드맵이 있을 때 build_roadmap은 전체 교체라 막힐 수 있으니 보통 view_roadmap 후 update_task/add_task를 써라."
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
