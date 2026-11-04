#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
On-disk library of cached YouCube media.

Media files stay named by video id. Titles and play times live in
library.json in the same data folder. Nothing in this module deletes files.
"""

# Built-in modules
from datetime import datetime, timezone
from json import JSONDecodeError, dumps, loads
from os import listdir, replace
from os.path import getsize, isfile, join
from re import compile as re_compile
from threading import Lock

# Local modules
import yc_utils
from yc_utils import (
    create_data_folder_if_not_present,
    get_audio_name,
    get_video_name,
    is_audio_already_downloaded,
    is_save,
    is_video_already_downloaded,
)

INDEX_NAME = "library.json"
_LOCK = Lock()
_VIDEO_NAME = re_compile(r"^(?P<id>.+)\((?P<width>\d+)x(?P<height>\d+)\)\.32vid$")
_YOUTUBE_URL = re_compile(
    r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/|v/)|youtu\.be/)"
    r"(?P<id>[A-Za-z0-9_-]{11})"
)
_YOUTUBE_ID = re_compile(r"^[A-Za-z0-9_-]{11}$")
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _now() -> str:
    """UTC timestamp with microseconds so back-to-back plays stay ordered."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _index_path() -> str:
    return join(yc_utils.DATA_FOLDER, INDEX_NAME)


def _read_index() -> dict:
    path = _index_path()
    if not isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = loads(handle.read())
    except (OSError, JSONDecodeError, UnicodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_index(index: dict) -> None:
    """Replace library.json atomically so a crash cannot leave a partial file."""
    create_data_folder_if_not_present()
    path = _index_path()
    temporary = path + ".tmp"
    payload = dumps(index, indent=2, sort_keys=True)
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        handle.buffer.flush()
    replace(temporary, path)


def record_playback(
    media_id: str,
    title: str = None,
    uploader: str = None,
    duration=None,
    url: str = None,
) -> None:
    """
    Store metadata for a played video and refresh last_played.

    first_cached is set only the first time this id is recorded.
    """
    if not media_id or not is_save(str(media_id)):
        return
    with _LOCK:
        index = _read_index()
        entry = index.get(media_id)
        if not isinstance(entry, dict):
            entry = {}
        now = _now()
        if not entry.get("first_cached"):
            entry["first_cached"] = now
        if title:
            entry["title"] = str(title)
        if uploader:
            entry["uploader"] = str(uploader)
        if isinstance(duration, (int, float)) and duration >= 0:
            entry["duration"] = int(duration)
        if url:
            entry["url"] = str(url)
        entry["last_played"] = now
        index[media_id] = entry
        _write_index(index)


def _scan_files() -> dict:
    """Group cached audio and video files by media id."""
    folder = yc_utils.DATA_FOLDER
    grouped = {}
    try:
        names = listdir(folder)
    except OSError:
        return grouped
    for name in names:
        path = join(folder, name)
        if not isfile(path) or name == INDEX_NAME or name.endswith(".tmp"):
            continue
        video = _VIDEO_NAME.match(name)
        if video and is_save(video.group("id")):
            media_id = video.group("id")
            slot = grouped.setdefault(
                media_id, {"has_audio": False, "videos": [], "bytes": 0}
            )
            slot["videos"].append(
                {
                    "width": int(video.group("width")),
                    "height": int(video.group("height")),
                    "bytes": _file_size(path),
                }
            )
            continue
        if name.endswith(".dfpwm"):
            media_id = name[: -len(".dfpwm")]
            if not is_save(media_id):
                continue
            slot = grouped.setdefault(
                media_id, {"has_audio": False, "videos": [], "bytes": 0}
            )
            slot["has_audio"] = True
            slot["bytes"] += _file_size(path)
    return grouped


def _file_size(path: str) -> int:
    try:
        return getsize(path)
    except OSError:
        return 0


def _entry(media_id: str, fileset: dict, meta: dict) -> dict:
    sizes = [
        {"width": item["width"], "height": item["height"]}
        for item in fileset["videos"]
    ]
    sizes.sort(key=lambda item: (item["width"], item["height"]))
    video_bytes = sum(item["bytes"] for item in fileset["videos"])
    return {
        "id": media_id,
        "title": meta.get("title") or media_id,
        "uploader": meta.get("uploader") or "",
        "duration": meta.get("duration"),
        "url": meta.get("url") or "",
        "has_audio": fileset["has_audio"],
        "video_sizes": sizes,
        "total_bytes": fileset["bytes"] + video_bytes,
        "last_played": meta.get("last_played"),
    }


def _sort_entries(entries: list, sort: str) -> list:
    if sort == "title":
        return sorted(entries, key=lambda item: (str(item["title"]).casefold(), item["id"]))
    dated = [item for item in entries if item["last_played"]]
    undated = [item for item in entries if not item["last_played"]]
    dated.sort(key=lambda item: item["last_played"], reverse=True)
    undated.sort(key=lambda item: item["id"])
    return dated + undated


def list_library(
    sort: str = "recent",
    offset: int = 0,
    limit: int = _DEFAULT_LIMIT,
    search: str = "",
) -> dict:
    """Return one page of cached media. Files with no metadata use the id as the title."""
    if sort not in ("recent", "title"):
        sort = "recent"
    offset = max(0, int(offset))
    limit = min(_MAX_LIMIT, max(1, int(limit)))
    needle = (search or "").casefold()

    with _LOCK:
        index = _read_index()
    entries = []
    for media_id, fileset in _scan_files().items():
        meta = index.get(media_id)
        if not isinstance(meta, dict):
            meta = {}
        title = meta.get("title") or media_id
        if needle and needle not in str(title).casefold():
            continue
        entries.append(_entry(media_id, fileset, meta))

    entries = _sort_entries(entries, sort)
    return {
        "action": "list_cache",
        "entries": entries[offset:offset + limit],
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "sort": sort,
    }


def resolve_cached_id(url: str) -> str:
    """Return a cached media id for a bare id or a YouTube URL, or an empty string."""
    if not url:
        return ""
    match = _YOUTUBE_URL.search(url)
    if match and is_save(match.group("id")):
        media_id = match.group("id")
        if is_audio_already_downloaded(media_id):
            return media_id
    if is_save(url) and is_audio_already_downloaded(url):
        return url
    with _LOCK:
        index = _read_index()
    for media_id, meta in index.items():
        if (
            isinstance(meta, dict)
            and meta.get("url") == url
            and is_save(media_id)
            and is_audio_already_downloaded(media_id)
        ):
            return media_id
    return ""


def serve_cached_request(url: str, width, height, is_video: bool):
    """
    Serve a fully cached request without calling yt-dlp.

    Returns None when the audio is missing, or when a requested video size
    is not on disk yet.
    """
    media_id = resolve_cached_id(url)
    if not media_id:
        return None
    if is_video and not is_video_already_downloaded(media_id, width, height):
        return None
    with _LOCK:
        index = _read_index()
    meta = index.get(media_id)
    if not isinstance(meta, dict):
        meta = {}
    record_playback(
        media_id,
        title=meta.get("title"),
        uploader=meta.get("uploader"),
        duration=meta.get("duration"),
        url=meta.get("url"),
    )
    response = {
        "action": "media",
        "id": media_id,
        "title": meta.get("title") or media_id,
        "like_count": None,
        "view_count": None,
    }
    files = [get_audio_name(media_id)]
    if is_video:
        files.append(get_video_name(media_id, width, height))
    return response, files


def download_url_for_cache(url: str) -> str:
    """
    Turn a cached YouTube id into a watch URL before yt-dlp runs.

    A bare id is otherwise treated as a text search. This only rewrites ids
    that already have cached audio, which is the library playback path when
    the requested video size still needs a download.
    """
    if _YOUTUBE_ID.match(url or "") and is_audio_already_downloaded(url):
        return "https://www.youtube.com/watch?v=" + url
    return url
