"""기존 평문 카카오 토큰을 일회성으로 암호화한다(마이그레이션).

배포에서 TOKEN_ENC_KEY를 설정한 뒤 1회 실행하면, users 테이블에 평문으로
남아 있던 kakao_access_token / kakao_refresh_token을 enc:v1: 암호문으로 바꾼다.
이미 암호화된 행(enc: 접두사)은 건너뛰므로 여러 번 실행해도 안전(idempotent).

사용:
    TOKEN_ENC_KEY=... uv run python scripts/encrypt_tokens.py
"""

from __future__ import annotations

from psycopg.rows import dict_row

from teamplay_talk.config import settings
from teamplay_talk.crypto import encrypt_token, is_encrypted
from teamplay_talk.db import conn


def main() -> None:
    if not settings.token_enc_key:
        raise SystemExit(
            "TOKEN_ENC_KEY가 설정되지 않았습니다. 먼저 키를 생성/설정하세요 "
            "(scripts/gen_token_key.py)."
        )

    updated = 0
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, kakao_access_token, kakao_refresh_token FROM users "
                "WHERE kakao_access_token IS NOT NULL OR kakao_refresh_token IS NOT NULL"
            )
            rows = cur.fetchall()

        for row in rows:
            access = row["kakao_access_token"]
            refresh = row["kakao_refresh_token"]
            # 둘 중 하나라도 평문이면 다시 쓴다. encrypt_token은 이미 암호문이면
            # 그대로 두므로, 한쪽만 평문이어도 안전하게 처리된다.
            if not (
                (access is not None and not is_encrypted(access))
                or (refresh is not None and not is_encrypted(refresh))
            ):
                continue
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE users SET kakao_access_token = %s, kakao_refresh_token = %s "
                    "WHERE id = %s",
                    (encrypt_token(access), encrypt_token(refresh), row["id"]),
                )
            updated += 1
        c.commit()

    print(f"암호화 완료 ✅ — {updated}개 행 갱신 (전체 {len(rows)}개 중)")


if __name__ == "__main__":
    main()
