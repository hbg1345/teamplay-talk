"""Google Drive REST 클라이언트 (Google API 직접 호출).

외부 SDK 없이 ``httpx`` 로 Drive REST API(v3)를 호출하는 순수 함수 모음이다.
**OAuth 자체는 호스트(PlayMCP)가 대행**한다 — 사용자 동의/토큰 발급/갱신은
PlayMCP가 처리하고, 발급된 Google access_token을 MCP 요청의 ``Authorization``
헤더로 전달한다. 이 모듈은 그 access_token을 받아 Drive를 호출하기만 한다.

스코프는 PlayMCP 등록 시 ``drive.file`` 을 쓰면 이 앱이 만든 파일/폴더만
접근하므로 동의 화면이 가볍고 사용자의 다른 개인 파일은 건드리지 않는다.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import httpx

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

FOLDER_MIME = "application/vnd.google-apps.folder"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def create_folder(
    access_token: str,
    name: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Drive에 폴더를 생성하고 메타데이터를 반환한다.

    Returns: ``{"id", "name", "webViewLink"}`` 형태(요청한 필드).
    """
    metadata: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        metadata["parents"] = [parent_id]
    params = {"fields": "id,name,webViewLink", "supportsAllDrives": "true"}
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{DRIVE_API}/files",
            params=params,
            headers={**_auth_headers(access_token), "Content-Type": "application/json"},
            content=json.dumps(metadata),
        )
    resp.raise_for_status()
    return resp.json()


def find_folder_by_name(access_token: str, name: str) -> dict[str, Any] | None:
    """이름이 일치하는 (이 앱이 만든) 폴더를 찾는다. 없으면 None.

    drive.file 스코프에서는 이 앱이 만든 폴더만 검색되므로, 같은 사용자가
    이전에 만든 방 폴더를 안전하게 재사용할 수 있다.
    """
    safe = name.replace("'", "\\'")
    params = {
        "q": (
            f"name = '{safe}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        ),
        "fields": "files(id,name,webViewLink)",
        "pageSize": 1,
        "spaces": "drive",
    }
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{DRIVE_API}/files", params=params, headers=_auth_headers(access_token)
        )
    resp.raise_for_status()
    files = resp.json().get("files", [])
    return files[0] if files else None


def upload_file(
    access_token: str,
    name: str,
    content: bytes,
    mime_type: str = "text/plain",
    parent_id: str | None = None,
) -> dict[str, Any]:
    """파일 내용을 multipart 업로드로 Drive에 생성한다.

    Returns: ``{"id", "name", "webViewLink", "mimeType"}``.
    """
    metadata: dict[str, Any] = {"name": name}
    if parent_id:
        metadata["parents"] = [parent_id]

    # Google Drive multipart 업로드는 multipart/related 형식을 요구한다
    # (httpx files= 의 multipart/form-data 가 아님). 본문을 직접 조립한다:
    #   part1 = 메타데이터(JSON), part2 = 파일 본문 — 순서·Content-Type으로 식별.
    boundary = f"tpt-{secrets.token_hex(16)}"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(metadata).encode("utf-8"),
        f"\r\n--{boundary}\r\n".encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    params = {
        "uploadType": "multipart",
        "fields": "id,name,webViewLink,mimeType",
        "supportsAllDrives": "true",
    }
    headers = {
        **_auth_headers(access_token),
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(DRIVE_UPLOAD, params=params, headers=headers, content=body)
    resp.raise_for_status()
    return resp.json()


def download_file(access_token: str, file_id: str) -> bytes:
    """파일 본문(bytes)을 내려받는다. (Google Docs 형식 파일은 export 필요 — 미지원)"""
    params = {"alt": "media", "supportsAllDrives": "true"}
    with httpx.Client(timeout=60) as client:
        resp = client.get(
            f"{DRIVE_API}/files/{file_id}",
            params=params,
            headers=_auth_headers(access_token),
        )
    resp.raise_for_status()
    return resp.content


def list_files(
    access_token: str,
    folder_id: str | None = None,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """폴더(또는 앱이 만든 전체) 안의 파일 목록을 반환한다.

    각 항목: ``{"id", "name", "mimeType", "webViewLink", "modifiedTime"}``.
    """
    q_parts = ["trashed = false"]
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")
    params = {
        "q": " and ".join(q_parts),
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{DRIVE_API}/files",
            params=params,
            headers=_auth_headers(access_token),
        )
    resp.raise_for_status()
    return resp.json().get("files", [])
