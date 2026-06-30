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
    token_enc_key: str | None
    public_base_url: str
    kakao_rest_api_key: str
    kakao_client_secret: str | None
    kakao_redirect_uri: str
    daily_task_digest_enabled: bool
    daily_task_digest_hour_kst: int
    daily_checkin_enabled: bool
    daily_checkin_hour_kst: int
    daily_report_enabled: bool
    daily_report_hour_kst: int

    @classmethod
    def from_env(cls) -> "Settings":
        port = int(os.getenv("PORT", "8000"))
        digest_hour = int(os.getenv("DAILY_TASK_DIGEST_HOUR_KST", "9"))
        checkin_hour = int(os.getenv("DAILY_CHECKIN_HOUR_KST", "21"))
        report_hour = int(os.getenv("DAILY_REPORT_HOUR_KST", "9"))
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=port,
            data_dir=os.getenv("DATA_DIR", "./data"),
            database_url=os.getenv("DATABASE_URL"),
            # 저장 토큰(카카오 access/refresh) 암호화용 Fernet 키. 미설정 시
            # 평문 저장으로 동작(하위호환). scripts/gen_token_key.py로 생성.
            token_enc_key=os.getenv("TOKEN_ENC_KEY") or None,
            # 폼 공유 링크 생성에 쓰는 외부 접근 URL (배포 시 실제 도메인으로 지정)
            public_base_url=os.getenv("PUBLIC_BASE_URL", f"http://localhost:{port}"),
            kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", ""),
            kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET") or None,
            kakao_redirect_uri=os.getenv(
                "KAKAO_REDIRECT_URI", f"http://localhost:{port}/auth/kakao/callback"
            ),
            daily_task_digest_enabled=os.getenv("DAILY_TASK_DIGEST_ENABLED", "").lower()
            in {"1", "true", "yes", "on"},
            daily_task_digest_hour_kst=max(0, min(23, digest_hour)),
            daily_checkin_enabled=os.getenv("DAILY_CHECKIN_ENABLED", "").lower()
            in {"1", "true", "yes", "on"},
            daily_checkin_hour_kst=max(0, min(23, checkin_hour)),
            daily_report_enabled=os.getenv("DAILY_REPORT_ENABLED", "").lower()
            in {"1", "true", "yes", "on"},
            daily_report_hour_kst=max(0, min(23, report_hour)),
        )


settings = Settings.from_env()
