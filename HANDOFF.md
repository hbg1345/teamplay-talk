# teamplay-talk 핸드오프 (2026-06-26)

> 다음 AI/세션이 이어받기 위한 문서. 박세원(PM)이 함봉구(hbg1345)와 만드는 **팀플 협업 MCP**.
> Kakao PlayMCP 공모전(마감 **2026-07-14**). repo: `hbg1345/teamplay-talk` (private).

## 지금 상태 (한 줄)
회의 일정 조율(When2meet 그리드) + 방별 결과 타임라인까지 구현·배포 완료. **다음 할 일 = 사용자가 PlayMCP에서 MCP 재등록 후 실제 동작 QC**, 그리고 PM 로드맵의 남은 축(진척 추적 등).

## 인프라 / 배포 (중요)
- **라이브**: `https://167.71.219.241.sslip.io` (DigitalOcean 드롭릿, Docker)
- **MCP 엔드포인트**: `https://167.71.219.241.sslip.io/mcp/`
- **배포 방법** (git 아님! rsync + docker):
  ```bash
  cd /Users/park/teamplay-talk
  rsync -az -e "ssh -o StrictHostKeyChecking=accept-new" \
    --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.env' \
    --exclude '*.pyc' --exclude 'data' ./ root@167.71.219.241:/root/teamplay-talk/
  ssh root@167.71.219.241 'cd /root/teamplay-talk && docker compose up -d --build'
  curl -s https://167.71.219.241.sslip.io/health   # → ok
  ```
- **라이브 도구 목록 확인** (MCP 핸드셰이크):
  ```bash
  B=https://167.71.219.241.sslip.io; M=$B/mcp/
  H=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
  SID=$(curl -s -D - -o /dev/null "${H[@]}" -X POST "$M" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"c","version":"1"}}}' | grep -i 'mcp-session-id:' | awk '{print $2}' | tr -d '\r')
  curl -s "${H[@]}" -H "mcp-session-id: $SID" -X POST "$M" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null
  curl -s "${H[@]}" -H "mcp-session-id: $SID" -X POST "$M" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  ```

## ⚠️ 가장 흔한 함정: PlayMCP 캐싱
서버를 배포해도 **PlayMCP(또는 클라)는 도구목록·instructions를 캐싱**한다. 새 도구/지침이 안 보이면
거의 항상 **PlayMCP에서 MCP를 삭제 후 재등록**해야 함. 라이브 서버는 위 핸드셰이크로 검증할 것
(라이브엔 맞게 떠 있는데 클라엔 옛날 게 뜨는 경우가 잦았음).

## 인증 (함봉구 방식 채택)
- PlayMCP가 카카오 OAuth를 직접 broker. 매 호출 `Authorization: Bearer <카카오 access_token>` 헤더.
- `identity.resolve_caller()` 가 헤더 토큰 → `kakao.get_user_info` → user upsert. 로그인 불필요.
- 핵심 픽스: PlayMCP가 /token에 client creds를 **Basic 헤더**로 보내는데 카카오는 **body**만 받음 →
  `kakao_token_proxy.py`(`/kakao/token`)가 Basic→body 변환. (구글은 제거됨)

## 현재 도구 16개
- **방(5)**: create_room, join_room, switch_room, rooms(목록/상세 통합), leave_room
- **폼/투표(5)**: create_poll, gather_opinions, get_poll_results, close_poll, send_form
- **역할(3)**: assign_roles, finalize_roles, set_roles
- **일정(1)**: schedule_meeting  ← 최신
- **알림(1)**: notify_room
- **대시보드(1)**: room_dashboard

## 핵심 아키텍처
- FastMCP v3 (Python), HTTP transport. 진입점 `teamplay-talk`→`server.main()`.
- **폼 엔진**: SurveyJS. `storage.create_form(schema_json,...)` → `/form/<id>?t=<token>` 매직링크.
  `forms_web.py`가 SurveyJS 임베드 페이지 렌더. 응답 `storage.save_response`(식별폼은 1인1표 upsert).
- **집계**: `storage.get_results` — 객관식 카운트/ranking 점수/rating 평균/text 목록/
  **matrixdropdown=O·X 그리드 집계(best_slots=X 0명 중 O 최다, 동점 전부)**.
- **트리거**: `triggers.py` 백그라운드 스케줄러(30s) — 폼 마감(시간/전원) 감지 → 작성자에게 카톡 nudge.
- **카톡 발송**: `kakao_store.send_with_refresh`(self-send + 401 시 토큰 refresh).
- **DB**: DigitalOcean Postgres. `schema.sql`.
- **방별 결과 타임라인**: `room_dashboard` → `/dashboard/rooms/{room_id}?token=...`.
  새 DB 없이 `forms.schema_json` + `form_responses.answers_json` 집계를 시간순 결과 카드로 렌더한다.

## 의사결정 흐름 3종 (server.py instructions에 가이드됨)
1. **역할분배**: assign_roles → [팀장 확인] → send_form → finalize_roles → [확인] → set_roles
   - LPT 균형배정(_balanced_assign): 모든 역할 커버, 난이도 균형(멤버엔 점수 숨김), 선호 tiebreak.
2. **회의 일정**: `schedule_meeting()` (기본 오늘부터 14일×9~22시 O/X 그리드, 가로=날짜 스크롤,
   세로=시간, 셀=O/X 드롭다운, 하단 기타건의사항) → [팀장 확인] → send_form →
   get_poll_results의 **best_slots**(동점 전부) 공지. AI는 인자 없이 호출만 하면 됨.
3. **의견수렴형(주제 등 막연한 것)**: gather_opinions(자유의견) → [nudge] → AI 항목화 →
   create_poll(복수선택 본투표) → 결과. (회의·후보 뻔한 건 위 단일단계로)
4. **방 결과 보기**: `room_dashboard()` → 결과 타임라인 링크. 방의 모든 투표/폼/일정 결과를
   생성된 순서대로 보여준다. 회의 일정 폼은 `best_slots`도 별도 요약.

## 반복된 교훈 (GPT-4.0이 클라 LLM이라 약함)
- 지침(`instructions`)이 GPT-4.0에 잘 안 닿음 → **도구 설명(docstring)에 흐름을 박아야** 동작.
  (회의가 떠넘겨지던 문제를 gather_opinions/schedule_meeting **진입 도구**로 해결한 패턴.)
- "사용자에게 후보 묻지 마, AI/멤버가 생성" 을 docstring에 명시.
- 확인 없이 발송/확정 금지(action_required로 게이트).

## 다음 할 일 (우선순위)
1. **[사용자] PlayMCP 재등록 후 QC**: "회의 일정 잡자" → schedule_meeting() 호출되는지,
   폼 그리드(가로 스크롤·O/X 드롭다운·기타칸) 렌더 정상인지. ← **지금 막힌 지점**
2. 그리드가 모바일에서 너무 빽빽하면: 기본 시간 9~18로 축소, 또는 forms_web에 `overflow-x:auto` CSS.
3. PM 로드맵 남은 축(`docs/PRODUCT_DIRECTION.md` 참고): **진척도 체크인**(스케줄러 재활용),
   정기 브리핑, 약속장소(멤버 위치→최적 중심점, 카카오맵 MCP 조합).
4. 기술부채: 카카오 토큰 평문 저장 → 암호화. 국외(DO 싱가포르) 개인정보 → PIPA 고지.

## 작업 규칙 (사용자 선호 — 반드시 지킬 것)
- **푸시는 명시적 허락 받고만** (이번엔 허락받아 푸시 완료, 미푸시 0).
- **시각 QC/스크린샷은 사용자가 함** — AI가 브라우저 QC 하면 토큰 낭비라고 싫어함.
- **토큰 의식적으로** — 과한 디버깅 금지. "키는 문제 없다"고 하면 그쪽 파지 말 것.
- 한국어로 소통.

## 메모리 파일
`/Users/park/.claude/projects/-Users-park-teamplay-talk/memory/` 의 MEMORY.md +
teamflow-mcp-project.md + teamplay-product-direction.md 참고.
