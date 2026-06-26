-- teamplay-talk 스키마
-- users ──< room_members >── rooms  (사용자와 방은 다대다, 연결 테이블에 역할 포함)

-- 사용자 (카카오 인증 신원)
CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    kakao_id   TEXT UNIQUE,                       -- 카카오 사용자 식별자 (OAuth 연동 시 채움)
    nickname   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 방 (팀플 워크스페이스)
CREATE TABLE IF NOT EXISTS rooms (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    owner_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,  -- 방장
    invite_code TEXT NOT NULL UNIQUE,                                     -- 참여용 초대 코드
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 방-사용자 연결 (다대다) + 역할
CREATE TABLE IF NOT EXISTS room_members (
    room_id   BIGINT NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    user_id   BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role      TEXT,                              -- 분배된 역할 (예: 자료조사, 발표)
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
);

-- user_id로 "이 사람이 속한 방" 조회를 빠르게
CREATE INDEX IF NOT EXISTS idx_room_members_user ON room_members (user_id);


-- ── 네이티브 폼/투표 (Google Forms 대체) ─────────────────────────────
-- forms ──< form_questions     (폼에 질문 N개)
-- forms ──< form_responses ──< form_answers   (응답 1건당 답 N개)

-- 폼/투표 (방에 속함)
CREATE TABLE IF NOT EXISTS forms (
    id          BIGSERIAL PRIMARY KEY,
    room_id     BIGINT NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    description TEXT,
    anonymous   BOOLEAN NOT NULL DEFAULT TRUE,    -- 익명 응답 여부
    closed      BOOLEAN NOT NULL DEFAULT FALSE,   -- 마감 여부
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 질문
CREATE TABLE IF NOT EXISTS form_questions (
    id       BIGSERIAL PRIMARY KEY,
    form_id  BIGINT NOT NULL REFERENCES forms (id) ON DELETE CASCADE,
    position INT NOT NULL,                         -- 표시 순서
    text     TEXT NOT NULL,
    qtype    TEXT NOT NULL,                        -- 'text' | 'single' | 'multi'
    options  JSONB                                 -- 객관식 선택지(문자열 배열). 주관식이면 NULL
);

-- 응답 1건 (제출 단위)
CREATE TABLE IF NOT EXISTS form_responses (
    id           BIGSERIAL PRIMARY KEY,
    form_id      BIGINT NOT NULL REFERENCES forms (id) ON DELETE CASCADE,
    respondent   TEXT,                             -- 익명이면 NULL
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 응답 내 개별 답 (집계 쉽도록 정규화; 복수선택이면 질문당 여러 row)
CREATE TABLE IF NOT EXISTS form_answers (
    id          BIGSERIAL PRIMARY KEY,
    response_id BIGINT NOT NULL REFERENCES form_responses (id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES form_questions (id) ON DELETE CASCADE,
    value       TEXT NOT NULL                      -- 선택지 텍스트 또는 주관식 답변
);

CREATE INDEX IF NOT EXISTS idx_form_questions_form ON form_questions (form_id);
CREATE INDEX IF NOT EXISTS idx_form_responses_form ON form_responses (form_id);
CREATE INDEX IF NOT EXISTS idx_form_answers_question ON form_answers (question_id);

-- ── Google Drive 연동 ────────────────────────────────────────────────
-- 인증(OAuth)은 호스트(PlayMCP)가 대행하고 access_token을 요청 헤더로 전달하므로
-- 서버는 토큰을 저장하지 않는다. 방 폴더도 호출 사용자의 Drive에서 이름으로
-- find-or-create 하므로 별도 매핑 테이블이 필요 없다. (전용 테이블 없음)


-- ── 카카오 알림 토큰 (users에 추가, 멤버별 self-push용) ────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_access_token     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_refresh_token    TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_token_expires_at TIMESTAMPTZ;

-- ── 현재 작업 중인 방(active room) — 사람당 1개 포인터 ──────────────────
-- 멤버십(room_members)은 그대로 두고, "지금 작업하는 방"만 가리킨다.
-- 방이 삭제되면 자동으로 NULL. 방에서 나가면(멤버십 삭제) leave_room이 직접 리셋.
ALTER TABLE users ADD COLUMN IF NOT EXISTS active_room_id BIGINT REFERENCES rooms (id) ON DELETE SET NULL;

-- ── 개인 액세스 토큰 (우리 OAuth 인가 서버가 발급 — 매 호출 신원) ─────────
-- 우리 /oauth/token이 발급하는 액세스 토큰. PlayMCP가 매 호출 헤더로 보낸다.
-- 원문은 저장하지 않고 sha256 해시만 저장(DB 유출 시에도 토큰 악용 불가).
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_users_token_hash ON users (token_hash);

-- ── 폼 엔진 v2 (SurveyJS JSON 모델 + 매직링크 + 트리거) ───────────────────
-- 폼 정의를 SurveyJS JSON으로 통째 저장(질문타입 무제한). 응답도 결과 객체 JSON.
ALTER TABLE forms ADD COLUMN IF NOT EXISTS schema_json     JSONB;          -- SurveyJS 폼 정의
ALTER TABLE forms ADD COLUMN IF NOT EXISTS creator_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL;  -- 드라이버(nudge 대상)
ALTER TABLE forms ADD COLUMN IF NOT EXISTS closes_at       TIMESTAMPTZ;    -- 마감 시각(트리거)
ALTER TABLE forms ADD COLUMN IF NOT EXISTS close_on_all    BOOLEAN NOT NULL DEFAULT FALSE;  -- 전원 응답 시 자동 마감
ALTER TABLE forms ADD COLUMN IF NOT EXISTS nudge_sent      BOOLEAN NOT NULL DEFAULT FALSE;  -- 드라이버 "확인하세요" 1회 발송

ALTER TABLE form_responses ADD COLUMN IF NOT EXISTS member_id    BIGINT REFERENCES users (id) ON DELETE SET NULL;  -- identified면 누구
ALTER TABLE form_responses ADD COLUMN IF NOT EXISTS answers_json JSONB;    -- SurveyJS 결과 {q1:..., q2:[...]}

-- 매직링크: 멤버별 고유 토큰 → 로그인 없이 신원 식별
CREATE TABLE IF NOT EXISTS form_invites (
    form_id   BIGINT NOT NULL REFERENCES forms (id) ON DELETE CASCADE,
    member_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token     TEXT NOT NULL UNIQUE,
    PRIMARY KEY (form_id, member_id)
);
CREATE INDEX IF NOT EXISTS idx_form_invites_token ON form_invites (token);
CREATE INDEX IF NOT EXISTS idx_form_responses_member ON form_responses (form_id, member_id);
