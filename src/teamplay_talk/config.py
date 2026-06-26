"""환경 설정 로딩.

환경 변수에서 서버 구동에 필요한 값을 읽어 ``settings`` 싱글턴으로 제공한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

# .env 자동 로딩. 기본 load_dotenv()는 호출 파일(config.py) 위치에서 위로
# 탐색하는데, 패키지가 site-packages에 설치되면 /app/.env를 못 찾는다.
# usecwd=True로 현재 작업 디렉터리(컨테이너=/app, 로컬=repo 루트) 기준 탐색한다.
# (배포 환경에 실제 환경변수가 따로 있으면 그게 우선)
load_dotenv(find_dotenv(usecwd=True))


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
    # 우리 OAuth 2.1 인가 서버가 PlayMCP(클라이언트)에 발급하는 자격증명
    oauth_client_id: str
    oauth_client_secret: str | None
    # 구글 OAuth (Drive 토큰 수집용 — 인가 서버가 카카오 다음에 체인)
    google_client_id: str | None
    google_client_secret: str | None

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
            oauth_client_id=os.getenv("OAUTH_CLIENT_ID", "playmcp"),
            oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET") or None,
            google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
        )


settings = Settings.from_env()
