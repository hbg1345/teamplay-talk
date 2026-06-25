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
    public_base_url: str
    kakao_rest_api_key: str
    kakao_client_secret: str | None
    kakao_redirect_uri: str

    @classmethod
    def from_env(cls) -> "Settings":
        port = int(os.getenv("PORT", "8000"))
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=port,
            data_dir=os.getenv("DATA_DIR", "./data"),
            database_url=os.getenv("DATABASE_URL"),
            # 폼 공유 링크 생성에 쓰는 외부 접근 URL (배포 시 실제 도메인으로 지정)
            public_base_url=os.getenv("PUBLIC_BASE_URL", f"http://localhost:{port}"),
            kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", ""),
            kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET") or None,
            kakao_redirect_uri=os.getenv(
                "KAKAO_REDIRECT_URI", f"http://localhost:{port}/auth/kakao/callback"
            ),
        )


settings = Settings.from_env()
