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
