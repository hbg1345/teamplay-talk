"""PostgreSQL 연결 관리.

``DATABASE_URL`` 로 커넥션 풀(psycopg-pool)을 만든다. DigitalOcean Managed
Postgres의 작은 플랜은 최대 동시 연결 수가 적으므로(약 22~25개) 풀 크기를
작게 유지해 한도를 넘지 않도록 한다.

사용:
    from .db import conn
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(...)
        c.commit()
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from .config import settings

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL이 설정되지 않았습니다. .env 또는 환경변수를 확인하세요."
    )

# open=False: import 시점에 연결하지 않고, 첫 conn() 호출 때 지연 오픈한다.
pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=5,
    open=False,
)

_opened = False


def conn():
    """풀에서 커넥션을 빌린다. (첫 호출 시 풀을 연다)

    ``with conn() as c:`` 형태로 사용하면 블록을 벗어날 때 자동 반환된다.
    """
    global _opened
    if not _opened:
        pool.open()
        _opened = True
    return pool.connection()


def close_pool() -> None:
    """커넥션 풀을 닫는다. (서버 종료 시 호출)"""
    global _opened
    if _opened:
        pool.close()
        _opened = False
