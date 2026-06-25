"""Google Drive 파일 도메인 도구 (Google API 직접 호출, 토큰은 호스트가 전달).

인증은 **호스트(PlayMCP)가 OAuth를 대행**한다. 사용자가 도구를 호출하면
PlayMCP가 Google access_token을 발급/갱신해 MCP 요청의 ``Authorization: Bearer``
헤더로 전달한다. 이 모듈은 그 토큰을 꺼내 본인 Drive에 파일을 쓰고/읽고/나열한다.

따라서 이 서버는 OAuth 토큰을 저장하지 않는다(상태 없음). 방 전용 폴더도
호출한 사용자의 Drive에서 이름으로 find-or-create 한다(per-user 토큰 +
drive.file 스코프에서는 다른 사람이 만든 폴더에 접근할 수 없기 때문).
"""

from __future__ import annotations

from base64 import b64encode
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from .. import gdrive, storage


class _NoToken(Exception):
    """요청에 Google access_token이 없음 (호스트가 OAuth를 안 거쳤거나 연결 안 됨)."""


def _google_token() -> str:
    """현재 MCP 요청의 Authorization 헤더에서 Google access_token을 꺼낸다.

    PlayMCP가 OAuth로 발급한 Google access_token을 Bearer로 전달한다는 전제.
    """
    headers = get_http_headers(include=["authorization"])
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    raise _NoToken


_NOT_CONNECTED = {
    "ok": False,
    "error": "Google Drive 인증 정보가 없습니다. PlayMCP에서 Google 계정 연결(권한 동의)을 먼저 진행해 주세요.",
}


def _room_folder_name(room_id: int) -> str:
    room = storage.get_room(room_id)
    return f"[팀플톡] {room['name']}" if room else f"[팀플톡] room-{room_id}"


def _ensure_room_folder(token: str, room_id: int) -> dict[str, Any]:
    """호출 사용자의 Drive에서 방 폴더를 찾고, 없으면 생성한다."""
    name = _room_folder_name(room_id)
    found = gdrive.find_folder_by_name(token, name)
    return found or gdrive.create_folder(token, name)


def register(mcp: FastMCP) -> None:
    """Google Drive 파일 도메인 도구를 등록한다."""

    @mcp.tool(
        name="drive_upload",
        annotations={
            "title": "Drive 파일 업로드",
            "readOnlyHint": False,
            "destructiveHint": False,  # 새 파일을 만들 뿐 기존 파일을 지우지 않음
            "idempotentHint": False,  # 호출마다 새 파일 생성
            "openWorldHint": True,  # 외부(Google Drive) 호출
        },
    )
    def drive_upload(
        name: str,
        content: str,
        room_id: int | None = None,
        mime_type: str = "text/plain",
    ) -> dict[str, Any]:
        """Uploads text content as a file to the caller's Google Drive via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 텍스트 내용을 파일로 만들어 호출 사용자의 Google
        Drive에 업로드하고 공유 링크를 반환한다. 인증은 호스트(PlayMCP)가 전달한
        Google 토큰으로 자동 처리된다. room_id를 주면 본인 Drive의 방 전용
        폴더에 저장한다(없으면 자동 생성).

        Args:
            name: 만들 파일 이름 (예: "회의록.txt")
            content: 파일에 담을 텍스트 내용
            room_id: 방 전용 폴더에 저장할 경우 방 ID (선택)
            mime_type: 파일 MIME 타입 (기본 text/plain)
        """
        try:
            token = _google_token()
        except _NoToken:
            return _NOT_CONNECTED

        parent_id = _ensure_room_folder(token, room_id)["id"] if room_id is not None else None
        result = gdrive.upload_file(
            token, name=name, content=content.encode("utf-8"),
            mime_type=mime_type, parent_id=parent_id,
        )
        return {
            "ok": True,
            "file_id": result["id"],
            "name": result["name"],
            "web_link": result.get("webViewLink"),
            "room_id": room_id,
        }

    @mcp.tool(
        name="drive_download",
        annotations={
            "title": "Drive 파일 다운로드",
            "readOnlyHint": True,  # Drive를 읽기만 함
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def drive_download(file_id: str) -> dict[str, Any]:
        """Downloads a file's content from the caller's Google Drive via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 file_id로 호출 사용자의 Google Drive 파일 내용을
        읽어 반환한다. 텍스트면 그대로, 바이너리면 base64로 반환한다.

        Args:
            file_id: 내려받을 Drive 파일 ID
        """
        try:
            token = _google_token()
        except _NoToken:
            return _NOT_CONNECTED

        data = gdrive.download_file(token, file_id)
        try:
            return {"ok": True, "file_id": file_id, "encoding": "utf-8", "content": data.decode("utf-8")}
        except UnicodeDecodeError:
            return {
                "ok": True,
                "file_id": file_id,
                "encoding": "base64",
                "content": b64encode(data).decode("ascii"),
            }

    @mcp.tool(
        name="drive_list",
        annotations={
            "title": "Drive 파일 목록",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def drive_list(room_id: int | None = None) -> dict[str, Any]:
        """Lists files in the caller's Drive (or a room's folder) via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 호출 사용자가 이 앱으로 만든 Drive 파일 목록을
        조회한다. room_id를 주면 본인 Drive의 그 방 전용 폴더 안만 조회한다.

        Args:
            room_id: 방 전용 폴더로 한정할 경우 방 ID (선택)
        """
        try:
            token = _google_token()
        except _NoToken:
            return _NOT_CONNECTED

        folder_id = None
        if room_id is not None:
            found = gdrive.find_folder_by_name(token, _room_folder_name(room_id))
            if found is None:
                return {"ok": True, "room_id": room_id, "files": [], "note": "방 폴더가 아직 없습니다."}
            folder_id = found["id"]

        files = gdrive.list_files(token, folder_id=folder_id)
        return {"ok": True, "room_id": room_id, "count": len(files), "files": files}

    @mcp.tool(
        name="create_room_folder",
        annotations={
            "title": "방 Drive 폴더 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,  # 이미 있으면 기존 폴더를 반환
            "openWorldHint": True,
        },
    )
    def create_room_folder(room_id: int) -> dict[str, Any]:
        """Creates (or reuses) a Google Drive folder for a teamplay-talk(팀플톡) room.

        팀플톡(teamplay-talk) 방 전용 Drive 폴더를 호출 사용자의 Drive에 만든다.
        이미 같은 이름의 폴더가 있으면 그 폴더를 반환한다.

        Args:
            room_id: 대상 방 ID
        """
        try:
            token = _google_token()
        except _NoToken:
            return _NOT_CONNECTED

        folder = _ensure_room_folder(token, room_id)
        return {
            "ok": True,
            "room_id": room_id,
            "folder_id": folder["id"],
            "web_link": folder.get("webViewLink"),
        }
