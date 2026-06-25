"""DB 연결 확인 스크립트.

DATABASE_URL로 실제 Postgres에 붙는지 확인한다.

실행:
    uv run python scripts/db_check.py
"""

from __future__ import annotations

import psycopg

from teamplay_talk.config import settings


def main() -> None:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL이 없습니다. .env를 확인하세요.")

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            (version,) = cur.fetchone()
    print("연결 성공 ✅")
    print(version)


if __name__ == "__main__":
    main()
