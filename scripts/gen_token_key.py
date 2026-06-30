"""TOKEN_ENC_KEY(Fernet 키)를 생성해 출력한다.

사용:
    uv run python scripts/gen_token_key.py
    # 출력된 값을 .env의 TOKEN_ENC_KEY=... 에 붙여넣는다.

주의: 이 키를 잃어버리면 기존 암호화 토큰을 복호화할 수 없다(사용자가 카카오를
다시 연결해야 함). 안전한 곳(배포 시크릿)에 보관하라.
"""

from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode("ascii"))
