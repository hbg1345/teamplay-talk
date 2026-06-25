"""DB 스키마 초기화 스크립트.

src/teamplay_talk/schema.sql 을 읽어 DATABASE_URL 의 DB에 적용한다.
(CREATE TABLE IF NOT EXISTS 라서 여러 번 실행해도 안전)

실행:
    uv run python scripts/init_db.py
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from teamplay_talk.config import settings

SCHEMA = Path(__file__).resolve().parent.parent / "src" / "teamplay_talk" / "schema.sql"


def main() -> None:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL이 없습니다. .env를 확인하세요.")

    sql = SCHEMA.read_text(encoding="utf-8")
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

        # 생성된 테이블 확인
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = [row[0] for row in cur.fetchall()]

    print("스키마 적용 완료 ✅")
    print("테이블:", tables)


if __name__ == "__main__":
    main()
