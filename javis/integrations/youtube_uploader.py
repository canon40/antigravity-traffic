# -*- coding: utf-8
"""YouTube Data API v3 — 숏폼 MP4 업로드."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_ROOT = Path(__file__).resolve().parent.parent


def _token_path() -> Path:
    p = (os.environ.get("YOUTUBE_TOKEN_FILE") or "").strip()
    if p:
        return Path(p)
    return _ROOT.parent / "data" / "youtube_token.json"


def _client_secrets_path() -> Path:
    p = (os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE") or "").strip()
    if p:
        return Path(p)
    return _ROOT.parent / "data" / "youtube_client_secrets.json"


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = _token_path()
    if token_file.is_file():
        creds = Credentials.from_authorized_user_file(str(token_file), _SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json(), encoding="utf-8")
        if creds and creds.valid:
            return creds

    cid = (os.environ.get("YOUTUBE_CLIENT_ID") or "").strip()
    secret = (os.environ.get("YOUTUBE_CLIENT_SECRET") or "").strip()
    refresh = (os.environ.get("YOUTUBE_REFRESH_TOKEN") or "").strip()
    if cid and secret and refresh:
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cid,
            client_secret=secret,
            scopes=_SCOPES,
        )
        creds.refresh(Request())
        return creds

    secrets = _client_secrets_path()
    if not secrets.is_file():
        raise FileNotFoundError(
            "YouTube OAuth 설정 필요: data/youtube_client_secrets.json 또는 "
            "YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN 환경변수"
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), _SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def youtube_configured() -> bool:
    if (os.environ.get("YOUTUBE_REFRESH_TOKEN") or "").strip():
        return bool((os.environ.get("YOUTUBE_CLIENT_ID") or "").strip())
    return _client_secrets_path().is_file() or _token_path().is_file()


def upload_youtube_short(
    video_path: str | Path,
    *,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "public",
    category_id: str = "22",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """MP4 → YouTube Shorts 업로드. 반환: {ok, video_id, url, error}."""
    emit = on_status or print
    path = Path(video_path)
    if not path.is_file():
        return {"ok": False, "error": f"영상 없음: {path}"}

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return {"ok": False, "error": "pip install google-api-python-client google-auth-oauthlib"}

    title = (title or path.stem)[:95]
    if "#shorts" not in title.lower() and "shorts" not in title.lower():
        title = f"{title} #Shorts"

    desc = (description or "").strip()
    if "#Shorts" not in desc:
        desc = (desc + "\n\n#Shorts").strip()

    tag_list = list(tags or [])
    for t in ("Shorts", "숏츠", "퍼마코트"):
        if t not in tag_list:
            tag_list.append(t)

    emit(f"[YouTube] 업로드: {path.name}")
    try:
        creds = _credentials()
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title,
                "description": desc[:4900],
                "tags": tag_list[:30],
                "categoryId": str(category_id or "22"),
            },
            "status": {
                "privacyStatus": privacy if privacy in ("public", "unlisted", "private") else "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                emit(f"[YouTube] 업로드 {pct}%")
        vid = response.get("id") or ""
        url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
        emit(f"[YouTube] 완료: {url}")
        return {"ok": bool(vid), "video_id": vid, "url": url}
    except Exception as exc:
        emit(f"[YouTube] 실패: {exc}")
        return {"ok": False, "error": str(exc)}
