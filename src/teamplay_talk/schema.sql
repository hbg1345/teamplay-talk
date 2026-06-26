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

-- ── 카카오 알림 토큰 (users에 추가, 멤버별 self-push용) ────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_access_token     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_refresh_token    TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_token_expires_at TIMESTAMPTZ;

-- ── 현재 작업 중인 방(active room) — 사람당 1개 포인터 ──────────────────
-- 멤버십(room_members)은 그대로 두고, "지금 작업하는 방"만 가리킨다.
-- 방이 삭제되면 자동으로 NULL. 방에서 나가면(멤버십 삭제) leave_room이 직접 리셋.
ALTER TABLE users ADD COLUMN IF NOT EXISTS active_room_id BIGINT REFERENCES rooms (id) ON DELETE SET NULL;
