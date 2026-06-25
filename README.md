# teamplay-talk

KAKAO PlayMCP 공모전 출품용 — 팀플(팀 프로젝트) 협업 MCP 서버.

팀플레이에 필요한 워크스페이스 생성·참여부터 역할 분배, 주제 분석 기반
로드맵, 진척 리포트까지를 자연어로 질의·실행합니다.

일정·의견수렴·장소정하기는 **Google Forms**, 회의록·자료·캘린더는
**Google MCP(Docs/Drive/Calendar/Meet)**가 담당하고, teamplay-talk는 그
산출물 링크를 방에 묶어 **팀 협업 허브**가 됩니다. (Google은 "생성", teamplay-talk는 "묶기")

## 제공 기능

- **방(워크스페이스)**: 팀플 워크스페이스 생성 / 초대 코드·링크로 참여 / 온보딩 초대 링크 발급
- **팀원·역할**: 역할 분배 / 랜덤 룰렛으로 무작위 배정
- **로드맵**: 주제 분석 → 로드맵 형성 / 로드맵 수정
- **리소스**: Google Forms/Docs/Drive/Calendar 등 외부 산출물 링크를 방에 등록·조회
- **리포트**: 데일리 리포트 / 팀 진척 대시보드 (등록된 리소스를 모아 요약)
- **외부 연동**: Git / 사용자 자신의 AI 연결

> 일정·투표·의견수렴·장소·회의록·파일·캘린더 등은 Google Forms / Google MCP에
> 위임하며 teamplay-talk가 직접 구현하지 않습니다. 호스트(Kakao/Claude)에 두
> MCP를 함께 연결해 사용합니다.

## 기술 스택

- **Python (FastMCP)** · **Postgres (DigitalOcean Managed)** · **DigitalOcean 상시 컨테이너**
- 전송: Streamable HTTP (Remote MCP) · MCP 엔드포인트 `http://<host>:<port>/mcp/`

---

## Tool 목록

> ✅ = 구현 완료(Postgres 연동), 그 외는 도메인 모듈 골격만 잡힌 **계획** 도구입니다.
> 관련 기능은 `action` 파라미터로 묶어 PlayMCP 권장(도구 3~10개, 최대 20개) 범위를 유지합니다.

### 방(워크스페이스)

**create_room** ✅ — 팀플 워크스페이스(방)를 생성합니다.
- `name`: string — 방 이름
- `owner`: string — 생성자(방장) 닉네임
- `description`: string — 방 설명 (선택)

**join_room** ✅ — 초대 코드로 방에 참여합니다.
- `invite_code`: string — 초대 코드
- `nickname`: string — 참여자 닉네임

**create_invite_link** — 온보딩용 초대 링크를 생성합니다. (계획)
- `room_id`: string — 대상 방 ID
- `expires_in`: integer — 만료 시간(분, 선택)

### 팀원·역할

**assign_roles** — 팀원에게 역할을 분배합니다.
- `room_id`: string — 대상 방 ID
- `assignments`: object — 팀원↔역할 매핑

**spin_roulette** — 랜덤 룰렛으로 무작위 선택/배정합니다.
- `room_id`: string — 대상 방 ID
- `options`: array — 후보 목록
- `count`: integer — 선택 개수 (기본 1)

### 로드맵

**build_roadmap** — 주제를 분석해 로드맵을 형성합니다.
- `room_id`: string — 대상 방 ID
- `topic`: string — 팀플 주제

**update_roadmap** — 로드맵을 수정합니다.
- `room_id`: string — 대상 방 ID
- `milestone_id`: string — 수정할 마일스톤
- `changes`: object — 변경 내용

### 리소스 (외부 산출물 링크)

**attach_resource** — Google Forms/Docs/Drive/Calendar 등 외부 산출물 링크를 방에 등록합니다.
- `room_id`: string — 대상 방 ID
- `kind`: string — `form` | `doc` | `drive` | `calendar` | `meet` | `etc`
- `title`: string — 자료 제목
- `url`: string — 산출물 링크

**list_resources** — 방에 등록된 리소스 목록을 조회합니다.
- `room_id`: string — 대상 방 ID
- `kind`: string — 종류 필터 (선택)

### 리포트

**daily_report** — 데일리 리포트를 생성합니다.
- `room_id`: string — 대상 방 ID
- `date`: string — 기준 일자 (선택)

**dashboard** — 팀 진척/현황을 대시보드로 요약합니다 (등록 리소스 포함).
- `room_id`: string — 대상 방 ID

### 외부 연동

**connect_git** — Git 저장소와 연동합니다.
- `room_id`: string — 대상 방 ID
- `repo_url`: string — 저장소 URL

**connect_ai** — 사용자 자신의 AI를 연결합니다.
- `room_id`: string — 대상 방 ID
- `endpoint`: string — AI 엔드포인트

---

## 개발

`.env`에 `DATABASE_URL`(DigitalOcean Managed PostgreSQL 연결 문자열)이 필요합니다.

```bash
uv venv
uv pip install -e .

# 1) DB 연결 확인
uv run python scripts/db_check.py
# -> 연결 성공 ✅ / PostgreSQL 18.x ...

# 2) 스키마 적용 (users / rooms / room_members) — 여러 번 실행해도 안전
uv run python scripts/init_db.py
# -> 스키마 적용 완료 ✅ / 테이블: ['room_members', 'rooms', 'users']

# 3) 서버 실행 (기본 0.0.0.0:8000)
teamplay-talk
# 또는
uv run python -m teamplay_talk.server
```

- MCP 엔드포인트: `http://localhost:8000/mcp/`
- 헬스체크: `http://localhost:8000/health`

## 아키텍처

도구는 **2계층**으로 분리한다 (도구는 SQL을 직접 다루지 않는다):

- **도구 층** `tools/*.py` — MCP 인터페이스(입력·출력). `storage.<함수>` 만 호출
- **저장 층** `storage.py` — 모든 SQL을 여기에 모음 (`db.py` 커넥션 풀 사용)

새 도구를 추가할 때는 `tools/rooms.py`의 `create_room` 을 템플릿으로 삼는다:
annotations 5종(title/readOnly/destructive/idempotent/openWorld) 모두 지정 +
description에 영문/국문 병기 및 서비스명 `teamplay-talk(팀플톡)` 포함.

## 로드맵

방(워크스페이스) ✅ → 팀원·역할 → 로드맵 → 리소스 연결 → 리포트 → 외부 연동 → 배포·PlayMCP 등록.
