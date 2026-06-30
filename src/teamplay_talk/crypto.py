"""저장 토큰(카카오 access/refresh) 앱 계층 암호화.

DB(users.kakao_access_token / kakao_refresh_token)에 토큰을 **평문**으로 두면
백업 유출·읽기권한 오설정 등으로 한 줄만 새도 사용자 대신 카카오 발송이 가능하다.
그래서 저장 직전에 Fernet(AES-128-CBC + HMAC)으로 암호화하고, 읽기 직후에 복호화한다.

설계:
- 키는 ``TOKEN_ENC_KEY`` 환경변수(Fernet 키). ``scripts/gen_token_key.py``로 생성.
- 암호문에는 ``enc:v1:`` 접두사를 붙여, 기존 평문 행과 명확히 구분한다.
  → 마이그레이션 중 평문/암호문이 섞여 있어도 복호화가 안전하게 동작(무중단).
- 키 미설정이면 **평문 통과**(개발 편의). 운영에서는 키를 반드시 설정한다.

쓰기:  ``encrypt_token(plain) -> "enc:v1:..."``  (키 없으면 plain 그대로)
읽기:  ``decrypt_token(stored) -> plain``        (접두사 없으면 레거시 평문으로 간주)
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_PREFIX = "enc:v1:"

_fernet: Fernet | None = None
_init_done = False


def _cipher() -> Fernet | None:
    """설정된 키로 Fernet 인스턴스를 1회 생성해 캐싱한다. 키 없으면 None."""
    global _fernet, _init_done
    if _init_done:
        return _fernet
    _init_done = True
    key = settings.token_enc_key
    if not key:
        print(
            "[crypto] TOKEN_ENC_KEY 미설정 — 저장 토큰을 평문으로 다룬다. "
            "운영 배포에는 키를 설정하라(scripts/gen_token_key.py)."
        )
        _fernet = None
        return None
    try:
        _fernet = Fernet(key.encode("ascii"))
    except Exception as exc:  # 잘못된 키 형식
        raise RuntimeError(
            f"TOKEN_ENC_KEY가 올바른 Fernet 키가 아닙니다: {type(exc).__name__}. "
            "scripts/gen_token_key.py로 다시 생성하세요."
        ) from exc
    return _fernet


def is_encrypted(value: str | None) -> bool:
    """저장값이 이 모듈이 만든 암호문인지(접두사 보유) 여부."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_token(plain: str | None) -> str | None:
    """평문 토큰을 암호문(``enc:v1:...``)으로 변환한다.

    None/빈 값은 그대로 통과. 키 미설정이면 평문 그대로 반환(하위호환).
    이미 암호문이면 이중 암호화하지 않고 그대로 둔다.
    """
    if not plain:
        return plain
    if is_encrypted(plain):
        return plain
    cipher = _cipher()
    if cipher is None:
        return plain
    token = cipher.encrypt(plain.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_token(stored: str | None) -> str | None:
    """저장값을 평문 토큰으로 되돌린다.

    - 접두사가 없으면 레거시 평문으로 간주해 그대로 반환.
    - 접두사가 있는데 키가 없거나 복호화 실패(키 회전/손상)면 None을 반환해
      '토큰 없음'으로 안전하게 처리되도록 한다(평문/암호문 노출 방지).
    """
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored  # 레거시 평문
    cipher = _cipher()
    if cipher is None:
        print("[crypto] 암호문 토큰을 만났지만 TOKEN_ENC_KEY가 없습니다.")
        return None
    try:
        return cipher.decrypt(stored[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        print("[crypto] 토큰 복호화 실패(키 불일치/손상) — 토큰 없음으로 처리.")
        return None


def decrypt_row_tokens(row: dict | None) -> dict | None:
    """행 dict의 kakao_access_token/kakao_refresh_token을 제자리 복호화한다.

    저장층 조회 함수에서 호출해, 하위 소비자가 항상 평문 토큰을 받게 한다.
    """
    if not row:
        return row
    for col in ("kakao_access_token", "kakao_refresh_token"):
        if col in row:
            row[col] = decrypt_token(row[col])
    return row
