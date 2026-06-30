"""저장 토큰 암호화 키 회전(rotate).

옛 키로 복호화 → 새 키로 재암호화해 DB를 갱신한다. 키를 교체했는데 옛 키로
암호화된 토큰이 DB에 남아 복호화가 안 될 때 사용한다.

  - 옛 키: 환경변수 TOKEN_ENC_KEY_OLD
  - 새 키: .env/환경변수 TOKEN_ENC_KEY (현재 운영 키)

사용:
    TOKEN_ENC_KEY_OLD=<옛키> uv run python scripts/rotate_token_key.py

여러 번 실행해도 안전: 이미 새 키로 풀리는 토큰은 건너뛴다.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from psycopg.rows import dict_row

from teamplay_talk.config import settings
from teamplay_talk.db import close_pool, conn

PREFIX = "enc:v1:"


def _dec(f: Fernet, value: str) -> str | None:
    try:
        return f.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def main() -> None:
    old_raw = os.getenv("TOKEN_ENC_KEY_OLD")
    new_raw = settings.token_enc_key
    if not old_raw or not new_raw:
        raise SystemExit("TOKEN_ENC_KEY_OLD(옛 키)와 TOKEN_ENC_KEY(새 키)가 모두 필요합니다.")
    old = Fernet(old_raw.encode("ascii"))
    new = Fernet(new_raw.encode("ascii"))

    def reencrypt(value: str | None) -> tuple[str | None, str]:
        """(새값, 상태). 상태: skip/rotated/unreadable."""
        if not value or not value.startswith(PREFIX):
            return value, "skip"           # 평문/None은 손대지 않음
        if _dec(new, value) is not None:
            return value, "skip"           # 이미 새 키로 풀림
        plain = _dec(old, value)
        if plain is None:
            return value, "unreadable"     # 옛 키로도 안 풀림(다른 키?)
        return PREFIX + new.encrypt(plain.encode("utf-8")).decode("ascii"), "rotated"

    rotated_rows = unreadable = 0
    try:
        with conn() as c:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, kakao_access_token, kakao_refresh_token FROM users "
                    "WHERE kakao_access_token IS NOT NULL OR kakao_refresh_token IS NOT NULL"
                )
                rows = cur.fetchall()

            for r in rows:
                new_a, sa = reencrypt(r["kakao_access_token"])
                new_r, sr = reencrypt(r["kakao_refresh_token"])
                if "unreadable" in (sa, sr):
                    unreadable += 1
                if "rotated" in (sa, sr):
                    with c.cursor() as cur:
                        cur.execute(
                            "UPDATE users SET kakao_access_token = %s, kakao_refresh_token = %s "
                            "WHERE id = %s",
                            (new_a, new_r, r["id"]),
                        )
                    rotated_rows += 1
            c.commit()
    finally:
        close_pool()

    print(f"회전 완료 ✅ — 갱신 {rotated_rows}행 / 전체 {len(rows)}행, 복구불가 {unreadable}행")


if __name__ == "__main__":
    main()
