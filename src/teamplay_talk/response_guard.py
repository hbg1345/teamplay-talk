"""툴 응답 크기 가드 미들웨어.

PlayMCP 네이티브 AI 채팅은 content part 크기 제한(경험상 ~350자)이 있어, 큰
응답이 "too large content part"로 막힌다(툴은 성공, 출력만 실패). 외부 AI는
제한이 없다.

이 미들웨어는 **실제로 대용량을 뱉는 특정 툴(roadmap_manage decompose)에만**
적용한다 — content 텍스트가 임계를 넘으면 큰 배열을 개수+샘플로 줄이고 대시보드
안내 힌트를 붙여 축소한다. room_manage/form_manage 등 일반 응답은 안내·다음단계가
잘리면 안 되므로 절대 건드리지 않는다.
- 데이터(DB)엔 영향 없음 — 축소는 채팅 출력 텍스트만.
- 긴 대시보드 URL은 넣지 않는다. 대신 AI가 room_dashboard를 호출해 안내하도록
  힌트만 준다(응답 예산을 아끼기 위함).
- DB/네트워크 호출이 없어 지연시간 영향 없음.

임계값은 아래 상수로 튜닝한다.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

MAX_CHARS = 350       # PlayMCP 네이티브 content part 한도(경험값). 넘으면 축소.
TARGET_CHARS = 300    # 축소 후 목표 길이(안전 마진).
ARRAY_SAMPLE = 3      # 큰 배열에서 남길 앞부분 개수.

_HINT = (
    "결과가 커서 요약만 반환됨. 사용자에겐 핵심만 짧게 말하고, 전체 상세는 "
    "room_dashboard를 호출해 대시보드 링크로 안내하세요."
)


# 압축을 적용할 큰-출력 툴 (name, action). 나머지 툴은 절대 건드리지 않는다.
# room_manage/form_manage 같은 일반 응답의 안내·다음단계가 잘리는 걸 막으려고,
# 실제로 대용량 트리를 뱉는 decompose에만 건다. 다른 툴이 넘치면 여기 추가.
_COMPACT_TARGETS: set[tuple[str, str | None]] = {
    ("roadmap_manage", "decompose"),
}


def _should_compact(context) -> bool:
    msg = getattr(context, "message", None)
    name = getattr(msg, "name", None)
    if name is None:
        return False
    args = getattr(msg, "arguments", None) or {}
    action = args.get("action") if isinstance(args, dict) else None
    return (name, action) in _COMPACT_TARGETS


def _text_len(result: ToolResult) -> int:
    for c in result.content or []:
        if isinstance(c, TextContent):
            return len(c.text or "")
    return 0


def _extract_dict(result: ToolResult) -> dict[str, Any]:
    data = result.structured_content
    if isinstance(data, dict):
        return data
    for c in result.content or []:
        if isinstance(c, TextContent):
            try:
                parsed = json.loads(c.text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"result_text": (c.text or "")[:120]}
    return {"result": str(data)[:120] if data is not None else ""}


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """큰 배열은 개수+샘플로 줄이고 힌트를 붙인다."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, list) and len(v) > ARRAY_SAMPLE:
            out[k] = {"_count": len(v), "_sample": v[:ARRAY_SAMPLE], "_truncated": True}
        elif isinstance(v, str) and len(v) > 160:
            out[k] = v[:157] + "…"
        else:
            out[k] = v
    out["_truncated"] = True
    out["chat_response_hint"] = _HINT
    return out


def _shrink_to_fit(data: dict[str, Any]) -> dict[str, Any]:
    compact = _compact(data)
    if len(json.dumps(compact, ensure_ascii=False)) <= TARGET_CHARS:
        return compact
    # 2차: 배열/큰 값 다 버리고 핵심 스칼라 + 힌트만.
    keep: dict[str, Any] = {}
    for k in ("ok", "error", "status", "count", "next"):
        v = data.get(k)
        if isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 120):
            keep[k] = v
    keep["_truncated"] = True
    keep["chat_response_hint"] = _HINT
    return keep


class ResponseSizeGuard(Middleware):
    """content 텍스트가 MAX_CHARS를 넘으면 축소해 네이티브 한도 초과를 막는다."""

    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        try:
            if not _should_compact(context):
                return result
            if _text_len(result) <= MAX_CHARS:
                return result
            compact = _shrink_to_fit(_extract_dict(result))
            text = json.dumps(compact, ensure_ascii=False)
            return ToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=compact,
                meta=getattr(result, "meta", None),
                is_error=getattr(result, "is_error", False),
            )
        except Exception:
            # 가드 실패가 툴 실패가 되면 안 된다.
            return result
