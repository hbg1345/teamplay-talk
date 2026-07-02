# teamplay-talk 핸드오프 (2026-06-30)

> 다음 AI/세션이 이어받기 위한 최신 정리. 박세원(PM)이 함봉구(hbg1345)와 만드는 **팀플 협업 MCP**.
> Kakao PlayMCP 공모전용. repo: `hbg1345/teamplay-talk` (private).

## 지금 상태

라이브 서버에 배포 완료. 팀 방, 카카오 OAuth, 폼/투표, 역할분배, 회의 일정, 약속 장소 후보 수집, 로드맵, 개인별 todo 분해, 카카오 공지/캘린더, 방별 대시보드, 방 삭제 유예까지 동작한다.

2026-06-30 현재 `main` 최신 배포 기준:
- 정식 도메인: `https://teamplay-talk.tech`
- 헬스체크: `https://teamplay-talk.tech/health`
- MCP 엔드포인트: `https://teamplay-talk.tech/mcp/`
- 대시보드는 React/liquid-glass 런타임을 주입하지 않도록 최적화했다.
- Docker 이미지에 `.env`를 굽던 이전 방식은 제거했고, `.dockerignore`에 `.env`를 추가했다.
- Codex Security diff scan 결과는 high 1건(`Dockerfile COPY .env`)이었고, 현재 main에서는 이미 수정된 상태다.
- 새 폼/투표 링크는 숫자 id 대신 `/r/{room_public_id}/f/{form_public_id}` 구조를 쓴다. 식별 폼은 `/r/{room_public_id}/f/{form_public_id}/{invite_token}`로 개인 토큰을 path에 붙인다. 기존 `/form/{id}`는 과거 링크 호환용으로 남겨둔다. URL 토큰이 access log에 남지 않도록 Uvicorn access log는 꺼두고 scheduler 로그만 직접 남긴다.

핵심 제품 방향은 **"팀원은 응답/실행만, 조율은 AI가 PM처럼"** 이다. 다만 AI 기억에 의존하지 않고 DB의 방/폼/역할/로드맵/todo 상태를 읽어 다음 행동을 이어가게 설계했다.

## 디자인 방향

현재 앱 표면은 **Kakao Workbench × Liquid Glass** 로 잡았다. 생산성 도구처럼 조밀하고 빨리 읽히되, Apple Liquid Glass 원칙처럼 글래스는 헤더/스티키 요약/컨트롤 같은 기능 레이어에만 두고 실제 응답·태스크·리포트 내용은 평평한 content layer로 유지한다.

- 먼저 적용된 표면: `ui_theme.py` 공통 테마, `forms_web.py` 투표/SurveyJS/회의시간 폼, `dashboard_web.py` 방별 타임라인 대시보드
- 유지 원칙: Kakao Big Sans는 제목, Kakao Small Sans는 본문/폼에 사용. 카드 radius 8px, warm neutral canvas, Teamplay charcoal은 작업공간 chrome, Kakao yellow는 CTA/선택 상태에만 사용, blue/red/amber는 상태 강조에 소량 사용
- Liquid Glass 원칙: glass-on-glass 금지, 리스트/테이블/반복 카드에는 blur를 걸지 않음, glass panel 안의 작은 배지는 투명 fill 수준으로만 처리
- 피할 것: 과한 랜딩페이지식 히어로, 장식용 오브젝트/블롭, 한 가지 색만 반복하는 팔레트, 초록색 계열 기본 CTA
- 홈페이지는 나중에 만들되, 현재 폼/대시보드 토큰을 기준으로 확장한다.
- 자세한 토큰/레이어 규칙은 `docs/DESIGN_SYSTEM.md`를 따른다.

## 인프라 / 배포

- 라이브: `https://teamplay-talk.tech`
- MCP 엔드포인트: `https://teamplay-talk.tech/mcp/`
- 이전 임시 주소: `https://167.71.219.241.sslip.io`
- 서버: DigitalOcean 드롭릿 + Docker Compose + Caddy
- DB: Postgres
- 배포는 git pull이 아니라 로컬에서 rsync 후 docker rebuild.

```bash
cd /Users/park/teamplay-talk
rsync -az -e "ssh -o StrictHostKeyChecking=accept-new" \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.env' \
  --exclude '*.pyc' --exclude 'data' ./ root@167.71.219.241:/root/teamplay-talk/
ssh root@167.71.219.241 'cd /root/teamplay-talk && docker compose up -d --build'
curl -fsS https://teamplay-talk.tech/health
```

`schema.sql` 변경 후 원격 DB 적용:

```bash
ssh root@167.71.219.241 'cd /root/teamplay-talk && docker compose exec -T app python - <<'"'"'PY'"'"'
from pathlib import Path
import psycopg
from teamplay_talk.config import settings
sql = Path("/app/src/teamplay_talk/schema.sql").read_text(encoding="utf-8")
with psycopg.connect(settings.database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
PY'
```

## PlayMCP 주의

- PlayMCP는 도구 목록/instructions를 캐싱하는 경우가 많다.
- 서버에는 새 도구가 보이는데 PlayMCP 대화에서 안 보이면 MCP 삭제 후 재등록이 필요할 수 있다.
- `codex/reduce-mcp-tool-count` 브랜치 기준 공개 MCP 도구 수는 **15개**다.
- 기존 38개 기능은 최대한 유지하되, 방/폼/역할/로드맵/task/데일리/캘린더는 domain hub 도구로 묶었다.
- PlayMCP가 캐시한 도구 목록이 남아 있으면 재등록 또는 MCP 새로고침이 필요할 수 있다.

## 채팅 응답 톤 / 함수명 노출 방지

- 사용자가 보는 PlayMCP 채팅에서는 `send_form`, `get_poll_results`, `member_tasks` 같은 내부 도구명을 그대로 말하지 않는다.
- 도구 응답에는 공개 도구 기준 `required_next_tool` + `required_next_action`이 들어갈 수 있지만, 채팅에서는 항상 자연어로 번역한다.
- 각 주요 도구 응답에 `user_prompt_examples`와 `chat_response_hint`를 넣었다.
- 예시 톤:
  - “이 폼 팀원들에게 보내줘”
  - “응답이 모이면 결과 정리해줘”
  - “확정된 회의 시간 공지해줘”
  - “역할별로 개인 todo까지 나눠줘”
- `codex/reduce-mcp-tool-count` 브랜치에서는 함수명 노출 방지와 도구 수 축소를 함께 반영했다.

## 인증

- PlayMCP가 카카오 OAuth를 broker하고, MCP 호출마다 `Authorization: Bearer <카카오 access_token>` 헤더가 들어온다.
- `identity.resolve_caller()`가 카카오 사용자 정보를 조회해 `users` upsert.
- 알림/캘린더용 카카오 토큰은 `users`에 저장.
- PlayMCP `/token` 요청이 Basic auth로 오던 문제는 `kakao_token_proxy.py`가 Basic → Kakao body 방식으로 변환해 해결.
- `kakao_token_proxy.py`는 성공한 token 응답을 카카오 `user/me`로 식별해 `users.kakao_access_token`/`kakao_refresh_token`에 저장한다. 팀원별 캘린더/알림 반복 실행은 이 저장 토큰에 의존한다.
- 이 저장 로직 이전에 권한동의한 팀원은 refresh token이 없을 수 있으므로, 캘린더 실패 시 PlayMCP에서 카카오 권한을 다시 연결해야 한다.

## 현재 공개 도구 15개

방/멤버:
- `room_manage` — create/join/switch/list/delete/restore/leave

공지:
- `notify_room`

폼/투표/의견수렴:
- `create_poll`, `gather_opinions`, `gather_locations`, `gather_task_opinions`
- `form_manage` — send/results/close

역할분배:
- `role_manage` — start/finalize/set

회의 일정:
- `schedule_meeting`

로드맵/todo:
- `roadmap_manage` — build/view/decompose/member_tasks/digest
- `task_manage` — add/update/delete

데일리 운영:
- `daily_manage` — create_checkin/apply_checkin/report

대시보드:
- `room_dashboard`

카카오 톡캘린더:
- `calendar_team` — room_event/task_events
- `calendar_personal` — create/list/get/update/delete

## 핵심 워크플로우

### 1. 팀 방

기본은 현재 작업 방(active room)이다.

```text
room_manage(action=create) / room_manage(action=join)
→ room_manage(action=switch)
→ room_manage(action=list) 로 현재 방과 멤버 확인
```

방 삭제:
- `room_manage(action=delete)`: soft delete, 유예 기간 후 purge
- `room_manage(action=restore)`: 유예 기간 내 복구
- `room_manage(action=leave)`: 마지막 멤버가 나가면 empty room 삭제 유예

방 생성 온보딩:
- `room_manage(action=create)` 응답에 `invite_share_text`, `join_command`, `onboarding`, `recommended_flow`, `suggested_next_actions`가 들어간다.
- 채팅 응답은 길게 설명하지 말고 “invite_share_text 공유 → 팀원 초대 → 주제 분석/로드맵 생성”을 먼저 안내한다.
- 기본 흐름은 `방 생성 → 팀원 초대 → 주제 분석/로드맵 생성 → 로드맵 의견수렴/수정 → 마일스톤 기반 역할분배 → 개인별 todo 분해`다.
- 역할분배를 먼저 하는 흐름은 사용자가 “이미 역할이 정해졌다/팀원 전문성이 확정됐다”고 명시한 경우만 예외로 둔다.

### 2. 역할분배

역할은 로드맵 단계명이 아니라 책임영역/워크스트림이어야 한다.

```text
assign_roles
→ 팀장 확인
→ send_form
→ get_poll_results
→ finalize_roles
→ 팀장 확인
→ set_roles
→ member_tasks(member='all') 확인
```

기능:
- `Role.slots`: 핵심 구현처럼 2명이 필요한 역할은 `slots: 2`.
- `finalize_roles`: 선호도 + 난이도 + slots로 균형 배정. 계산만 하고 저장하지 않음.
- `set_roles`: DB에 역할 저장, 역할 결정 기록 저장, 기존 role-only todo를 실제 멤버에게 sync.
- `assign_roles`는 `대회 주제 선정`, `최종 제출` 같은 로드맵 단계명을 역할로 쓰면 거절한다.

### 3. 로드맵과 개인 todo

이제 두 레이어가 분리되어 있다.

- `build_roadmap`: 큰 단계, 즉 `task_type='milestone'`
- `decompose_roadmap`: milestone 아래 실제 실행 todo, 즉 `task_type='todo'`
- `member_tasks`: 실제 개인별 todo만 조회

정상 흐름:

```text
build_roadmap
→ gather_task_opinions(scope='roadmap') 또는 바로 다음 단계
→ set_roles
→ decompose_roadmap
→ member_tasks(member='all', window='week')
→ 확인 후 daily_task_digest 또는 calendar_create_task_events
```

중요:
- `daily_task_digest`는 분배 도구가 아니다. 이미 멤버에게 배정된 todo를 카톡으로 공지하는 도구다.
- 사용자가 "팀원별로 나눠줘"라고 하면 `daily_task_digest`부터 호출하면 안 된다.
- 먼저 `set_roles`가 끝났는지 확인하고, role-only todo가 있으면 sync 후 `member_tasks`로 사용자에게 보여준다.

최근 보강:
- `storage.sync_task_assignees_by_roles(room_id)` 추가.
- 역할명으로만 저장된 todo를 현재 `room_members.role` 기준으로 실제 멤버에게 연결한다.
- 같은 역할 담당자가 여러 명이면 현재 todo 수가 적은 멤버에게 분산한다.
- role-only todo가 남으면 `needs_role_assignment: true`, `required_next_tool: set_roles`가 나온다.

### 3-1. 데일리 체크인/리포트

밤 체크인 → 아침 리포트 루프다. 기본 자동 스케줄러는 꺼져 있고, env로 켤 수 있다.

```text
create_daily_checkin
→ send_form
→ apply_daily_checkin(dry_run=true)
→ 확인 후 apply_daily_checkin(dry_run=false)
→ daily_report(publish=false/true)
→ 필요하면 daily_task_digest
```

특징:
- 체크인 폼은 식별 폼이다. 새 폼은 `밀린 일 중 오늘 처리한 것`, `오늘 해야 했던 일 중 끝낸 것`, `앞으로 예정된 일 중 미리 끝낸 것`, `기타 메모`만 받는다.
- `apply_daily_checkin`은 두 체크박스에서 선택된 todo를 `done`으로 반영한다. 안 끝낸 오늘 일은 다음 날부터 overdue가 되어 다음 체크인의 밀린 일 목록에 잡힌다.
- `daily_report`는 기본적으로 전날 체크인을 오늘 리포트에 반영하고 `daily_reports`에 저장한다.
- 대시보드는 데일리 리포트를 별도 상단 패널이 아니라 폼/결정 기록과 같은 타임라인 이벤트로 보여준다.
- 자동화 env:
  - `DAILY_CHECKIN_ENABLED=true`, `DAILY_CHECKIN_HOUR_KST=21`
  - `DAILY_REPORT_ENABLED=true`, `DAILY_REPORT_HOUR_KST=9`
  - `DAILY_TASK_DIGEST_ENABLED=true`, `DAILY_TASK_DIGEST_HOUR_KST=9`
- 2026-06-30 기준 서버 env는 위 세 자동화가 모두 켜진 상태로 확인했다.
- 자동화가 조용히 스킵돼 원인 파악이 어려웠기 때문에, scheduler 로그에 daily_task_digest/daily_checkin/daily_report별 sent/failed/missing_token/skipped 수를 남기도록 보강했다.

### 4. 회의 일정

```text
schedule_meeting
→ 팀장 확인
→ send_form
→ get_poll_results
→ best_slots 중 확정
→ notify_room
→ calendar_create_room_event
```

특징:
- SurveyJS `matrixdropdown` O/X 그리드.
- `best_slots`: X 0명 중 O 최다인 모든 동점 시간.
- 모바일은 날짜 가로 스크롤, 시간 세로축.

### 5. 약속 장소

장소는 긴 자유서술 한 칸 대신 전용 폼을 쓴다.

```text
gather_locations
→ send_form
→ get_poll_results
→ AI가 location_1~5 정규화
→ create_poll 복수선택 본투표
→ send_form
→ get_poll_results
→ notify_room
```

중요:
- 카카오맵 MCP로 "중간역/개인별 이동시간 자동 추천"을 약속하지 말 것.
- 카카오맵/지도 MCP가 보이면 장소명·역명·주소 확인과 중복 후보 정규화에만 보조적으로 사용.
- 없으면 "카카오맵 MCP가 있으면 장소명/주소 확인이 더 정확해지고, 지금은 제출된 텍스트 기준으로 후보를 정리해 투표할 수 있다"라고 말한다.

### 6. 중간 의견수렴

일반:

```text
gather_opinions
→ send_form
→ get_poll_results
→ AI 항목화
→ create_poll 본투표
```

로드맵/todo 전용:

```text
gather_task_opinions(scope='roadmap'|'todo'|'blockers'|'scope')
→ send_form
→ get_poll_results
→ AI 정규화
→ decompose_roadmap / add_task / update_task / create_poll
→ member_tasks
```

### 7. 대시보드

`room_dashboard`가 방별 대시보드 링크를 반환한다.

보여주는 것:
- 최신 폼/투표/체크인/데일리 리포트/확정 결정 통합 타임라인
- role/todo/roadmap 상태
- milestone 수, todo 수, 미배정/role-only todo 수
- 캘린더 후보
- decision log

## DB/스키마 주요 추가

- `rooms.status`, `deleted_at`, `purge_after`, `deleted_by_user_id`, `delete_reason`
- `form_responses` 식별 폼 1인 1응답 unique upsert
- `tasks.task_type`: `milestone` / `todo`
- `tasks.parent_task_id`: todo가 속한 상위 milestone
- `task_digest_sends`: 일일 todo digest 중복 방지
- `room_decisions`: 회의시간/장소/역할 등 확정 결정 기록

## 보안/권한

- `tools/guards.py` 추가.
- 주요 도구는 호출자가 해당 active room/form 멤버인지 검사.
- 식별 폼은 멤버별 개인 링크 사용.
- `send_form`/`notify_room`은 실제 `sent_to`가 없으면 성공처럼 말하지 않도록 보강.

## 서버 instructions 원칙

`server.py` instructions가 매우 중요하다. GPT-4.0이 도구 설명을 약하게 따르는 경향이 있어, 중요한 흐름은 docstring과 tool response의 `next`, `suggested_next_actions`, `chat_response_hint`에도 중복해 박아두었다.

핵심 지침:
- 도구 호출 뒤 사용자에게 **현재 상태 + 다음 선택지 2~4개**를 말하라.
- `sent=false` 상태에서는 절대 "보냈다"라고 말하지 말라.
- `finalize_roles`는 저장이 아니다. `set_roles` 전에는 역할 확정이라고 말하지 말라.
- todo 분배와 digest를 혼동하지 말라.
- 장소는 중간역 추천을 약속하지 말라.

## 최근 QC에서 잡힌 문제와 해결

1. 역할명 todo가 실제 멤버에게 배정되지 않아 `daily_task_digest`가 안 옴.
   - 해결: `sync_task_assignees_by_roles`, `set_roles` 후 자동 sync, `daily_task_digest` 실패 이유 반환.

2. AI가 todo 초안을 만들고 사용자에게 안 보여준 뒤 바로 공지하려 함.
   - 해결: `decompose_roadmap` 응답에 `required_next_tool`, `needs_role_assignment`, `member_tasks` 유도.

3. 장소 기능이 카카오맵 MCP로 중간역 추천을 과하게 약속.
   - 해결: `gather_locations` 전용 폼 + 카카오맵은 장소명/주소 확인 보조로만 안내.

4. PlayMCP에서 도구 생성만 하고 보냈다고 말함.
   - 해결: `sent=false`, `required_next_tool='send_form'`, `do_not_claim_sent_before_send_form` 패턴 추가.

## 다음 할 일

1. PlayMCP에서 재등록 후 전체 워크플로우 QC:
   - 역할분배 → role_manage(action=set) → roadmap_manage(action=decompose) → roadmap_manage(action=member_tasks) → roadmap_manage(action=digest)
   - schedule_meeting → best_slots → calendar_team(action=room_event)
   - gather_locations → 본투표 → notify_room

2. 도구 수 정리:
   - `codex/reduce-mcp-tool-count` 브랜치에서 공개 도구 수를 38개에서 15개로 줄였다.
   - 다음 단계는 PlayMCP 재등록 후 실제 라우팅 QC다.

3. 개인정보/운영:
   - 카카오 토큰 저장 암호화는 구현됨(`TOKEN_ENC_KEY`).
   - 이전에 `.env`를 Docker 이미지에 굽던 방식은 제거됨. 이미 외부에 올라간 이미지가 있다면 관련 secret 회전 필요.
   - 해외 서버(DO) 개인정보 고지.
   - 로그/토큰 노출 점검.

4. 제품 polish:
   - 대시보드에서 role-only todo를 더 눈에 띄게 표시.
   - `member_tasks` 결과를 더 예쁜 마크다운 요약으로 반환.
   - 장소 투표 결과를 decision log에 더 명확히 기록.

## 사용자 선호

- 한국어로 짧고 실용적으로 소통.
- 사용자가 "배포해/푸시해" 하면 실제로 끝까지 실행.
- 시각 QC는 사용자가 직접 하는 편을 선호.
- 토큰 낭비 싫어함. 이미 아니라고 한 원인을 계속 파지 말 것.
- 욕이 섞여도 보통 답답해서 그러는 것. 감정적으로 받아치지 말고 바로 고치기.
