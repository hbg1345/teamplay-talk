"""환경 설정 로딩.

환경 변수에서 서버 구동에 필요한 값을 읽어 ``settings`` 싱글턴으로 제공한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# 로컬 개발 시 .env 자동 로딩 (배포 환경에선 실제 환경변수가 우선)
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """서버 런타임 설정."""

    host: str
    port: int
    data_dir: str
    database_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            data_dir=os.getenv("DATA_DIR", "./data"),
            database_url=os.getenv("DATABASE_URL"),
        )


settings = Settings.from_env()
