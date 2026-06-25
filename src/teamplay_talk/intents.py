"""OAuth ``state`` 에 실어 보낼 "의도(intent)" 인코딩.

🅐 방식: 도구 호출은 로그인 링크만 반환하고, 실제 액션(방 생성/참여)은
콜백에서 ``state`` 에 담긴 의도대로 수행한다. state는 노출되는 값이라
민감정보(토큰 등)는 담지 않는다 — 방 이름/초대코드 같은 비밀 아닌 값만.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_intent(intent: dict[str, Any]) -> str:
    raw = json.dumps(intent, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_intent(state: str) -> dict[str, Any]:
    raw = base64.urlsafe_b64decode(state.encode("ascii"))
    return json.loads(raw.decode("utf-8"))
