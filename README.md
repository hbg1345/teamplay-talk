# teamplay-talk

KAKAO PlayMCP 공모전 출품용 — 팀플(팀 프로젝트) 협업 MCP 서버.

팀플레이에 필요한 워크스페이스 생성·참여부터 역할 분배, 주제 분석 기반
로드맵, 진척 리포트까지를 자연어로 질의·실행합니다.

일정·의견수렴·장소정하기는 **Google Forms**, 회의록·자료·캘린더는
**Google MCP(Docs/Drive/Calendar/Meet)**가 담당하고, teamplay-talk는 그
산출물 링크를 방에 묶어 **팀 협업 허브**가 됩니다. (Google은 "생성", teamplay-talk는 "묶기")

## 제공 기능

- **방(워크스페이스)**: 팀플 워크스페이스 생성 / 초대 코드로 참여 / 팀원 공유용 참여 문구 발급
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
- 응답: `invite_code`, `join_command`, `invite_share_text`

**join_room** ✅ — 초대 코드로 방에 참여합니다.
- `invite_code`: string — 초대 코드
- `nickname`: string — 참여자 닉네임

초대 링크는 별도 웹 로그인 흐름 대신 `create_room`/`rooms(invite_code)` 응답의 `invite_share_text`를 공유하는 방식으로 운영합니다.

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

### 파일 (Google Drive · 직접 연동) ✅

> **Google Drive API를 직접** 호출해 호출 사용자의 Drive에 파일을 읽고 씁니다
> (Google MCP 미사용). 스코프는 `drive.file`(이 앱이 만든 파일/폴더만 접근)이라
> 사용자의 다른 개인 파일은 건드리지 않습니다.
>
> **인증은 호스트(PlayMCP)가 대행**합니다. PlayMCP가 Google OAuth로 발급한
> access_token을 MCP 요청의 `Authorization: Bearer` 헤더로 전달하고, 서버는
> 그 토큰을 그대로 사용합니다. 따라서 서버는 토큰을 저장하지 않습니다(상태 없음).

**drive_upload** ✅ — 텍스트 내용을 파일로 Drive에 업로드합니다.
- `name`: string — 파일 이름
- `content`: string — 파일 내용
- `room_id`: integer — 방 전용 폴더에 저장 (선택, 폴더 없으면 자동 생성)
- `mime_type`: string — MIME 타입 (기본 `text/plain`)

**drive_download** ✅ — file_id로 파일 내용을 읽어옵니다.
- `file_id`: string — Drive 파일 ID

**drive_list** ✅ — Drive(또는 방 폴더) 안 파일 목록을 조회합니다.
- `room_id`: integer — 방 폴더로 한정 (선택)

**create_room_folder** ✅ — 방 전용 Drive 폴더를 생성(있으면 재사용)합니다.
- `room_id`: integer — 대상 방 ID

> 방 폴더는 호출 사용자 Drive에서 이름으로 find-or-create 합니다. per-user 토큰 +
> `drive.file` 스코프 특성상 **방 폴더는 사용자별로 각자 Drive에 생기며 공유되지
> 않습니다.** 팀원 간 공유가 필요하면 폴더를 멤버에게 공유하거나 공유 드라이브를
> 쓰는 별도 작업이 필요합니다.

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

### 저장 토큰 암호화 (TOKEN_ENC_KEY)

DB(`users.kakao_access_token` / `kakao_refresh_token`)에 들어가는 카카오 OAuth
토큰은 앱 계층에서 **Fernet으로 암호화**해 저장합니다. 운영 배포에는 키를
설정하세요. (미설정 시 평문 저장으로 동작 — 개발 편의)

```bash
# 1) 키 생성 후 .env의 TOKEN_ENC_KEY=... 에 붙여넣기
uv run python scripts/gen_token_key.py

# 2) (기존 배포만) 평문으로 남아 있던 토큰을 일회성 암호화 — 여러 번 실행해도 안전
uv run python scripts/encrypt_tokens.py
```

> 암호문에는 `enc:v1:` 접두사가 붙어 평문/암호문이 섞여 있어도 읽기가 무중단으로
> 동작합니다. **키를 분실하면 기존 토큰은 복호화 불가**(사용자가 카카오 재연결
> 필요)이므로 배포 시크릿에 안전히 보관하세요.

### Google Drive OAuth (PlayMCP 등록 시 설정)

Drive 연동의 OAuth는 **호스트(PlayMCP)가 대행**하므로 서버 `.env`에 Google
자격증명을 둘 필요가 없습니다. 대신 PlayMCP MCP 등록 폼의 **인증 방식: OAuth**
에 아래를 입력합니다.

1. Google Cloud Console > Drive API 사용 설정(Enable) + OAuth 2.0 클라이언트 ID 발급
2. PlayMCP 등록 폼에 입력:
   - **Client ID / Client Secret** — Google 클라이언트 값
   - **Authorization Endpoint URL** — `https://accounts.google.com/o/oauth2/v2/auth`
   - **Token Endpoint URL** — `https://oauth2.googleapis.com/token`
   - **Scope** — `https://www.googleapis.com/auth/drive.file`
   - **Grant Type** — `AUTHORIZATION_CODE`
3. MCP 등록 후 발급된 `mcpId`로 Google 클라이언트의 **승인된 리디렉션 URI**에
   `https://playmcp.kakao.com/api/v1/applied-mcps/{mcpId}/authorize/oauth:callback` 등록
4. (권장) 사용자에게 '개인정보 제3자 제공 동의' 안내

서버는 PlayMCP가 `Authorization: Bearer`로 전달한 Google access_token을 읽어
Drive를 호출합니다. (refresh/만료 갱신도 PlayMCP가 처리)

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
