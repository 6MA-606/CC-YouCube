"""Cached-media library index and list_cache."""

import asyncio
import json
from pathlib import Path

import yc_utils
from yc_download import download
from yc_library import list_library, record_playback
from youcube import Actions


def _use_data(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(yc_utils, "DATA_FOLDER", str(path))


def _touch(folder: Path, name: str, payload: bytes = b"x") -> None:
    target = folder / name
    target.write_bytes(payload)


def test_metadata_round_trip_and_files_without_metadata(monkeypatch, tmp_path):
    _use_data(monkeypatch, tmp_path)
    _touch(tmp_path, "58TbfRY2R8Y.dfpwm", b"audio")
    _touch(tmp_path, "58TbfRY2R8Y(158x72).32vid", b"video-bytes")
    _touch(tmp_path, "oldfile12.dfpwm", b"ab")
    record_playback(
        "58TbfRY2R8Y",
        title="Example Song",
        uploader="Example Channel",
        duration=212.4,
        url="https://www.youtube.com/watch?v=58TbfRY2R8Y",
    )
    index = json.loads((tmp_path / "library.json").read_text(encoding="utf-8"))
    saved = index["58TbfRY2R8Y"]
    assert saved["title"] == "Example Song"
    assert saved["uploader"] == "Example Channel"
    assert saved["duration"] == 212
    assert saved["first_cached"]
    first = saved["first_cached"]
    assert saved["last_played"]

    record_playback("58TbfRY2R8Y", title="Example Song")
    index = json.loads((tmp_path / "library.json").read_text(encoding="utf-8"))
    assert index["58TbfRY2R8Y"]["first_cached"] == first
    assert index["58TbfRY2R8Y"]["last_played"] != ""
    assert not (tmp_path / "library.json.tmp").exists()

    page = list_library(sort="title", search="example")
    assert page["total"] == 1
    entry = page["entries"][0]
    assert entry["id"] == "58TbfRY2R8Y"
    assert entry["has_audio"] is True
    assert entry["video_sizes"] == [{"width": 158, "height": 72}]
    assert entry["total_bytes"] == len(b"audio") + len(b"video-bytes")

    unnamed = list_library(sort="title", search="oldfile")
    assert unnamed["entries"][0]["title"] == "oldfile12"
    assert unnamed["entries"][0]["uploader"] == ""
    assert unnamed["entries"][0]["duration"] is None
    assert unnamed["entries"][0]["last_played"] is None


def test_sort_paging_and_recent_order(monkeypatch, tmp_path):
    _use_data(monkeypatch, tmp_path)
    _touch(tmp_path, "aaaaaaaaaaa.dfpwm")
    _touch(tmp_path, "bbbbbbbbbbb.dfpwm")
    _touch(tmp_path, "ccccccccccc.dfpwm")
    record_playback("bbbbbbbbbbb", title="Bravo")
    record_playback("aaaaaaaaaaa", title="Alpha")

    recent = list_library(sort="recent", offset=0, limit=1)
    assert recent["total"] == 3
    assert recent["entries"][0]["id"] == "aaaaaaaaaaa"
    second = list_library(sort="recent", offset=1, limit=1)
    assert second["entries"][0]["id"] == "bbbbbbbbbbb"
    untitled = list_library(sort="recent", offset=2, limit=1)
    assert untitled["entries"][0]["id"] == "ccccccccccc"
    assert untitled["entries"][0]["title"] == "ccccccccccc"

    titled = list_library(sort="title", limit=10)
    assert [item["title"] for item in titled["entries"]] == [
        "Alpha",
        "Bravo",
        "ccccccccccc",
    ]


def test_cached_id_and_watch_url_skip_download(monkeypatch, tmp_path):
    _use_data(monkeypatch, tmp_path)
    _touch(tmp_path, "58TbfRY2R8Y.dfpwm", b"cached-audio")
    _touch(tmp_path, "58TbfRY2R8Y(10x6).32vid", b"cached-video")
    record_playback(
        "58TbfRY2R8Y",
        title="Cached",
        uploader="Channel",
        duration=12,
        url="https://www.youtube.com/watch?v=58TbfRY2R8Y",
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("yt-dlp should not run for a cache hit")

    monkeypatch.setattr("yc_download.YoutubeDL", fail_if_called)
    audio_out, audio_files = download(
        "58TbfRY2R8Y", None, None, None, None, None
    )
    assert audio_out["action"] == "media"
    assert audio_out["id"] == "58TbfRY2R8Y"
    assert audio_out["title"] == "Cached"
    assert audio_files == ["58TbfRY2R8Y.dfpwm"]

    video_out, video_files = download(
        "https://www.youtube.com/watch?v=58TbfRY2R8Y",
        None,
        None,
        10,
        6,
        None,
    )
    assert video_out["action"] == "media"
    assert "58TbfRY2R8Y(10x6).32vid" in video_files
    played = json.loads((tmp_path / "library.json").read_text(encoding="utf-8"))
    assert played["58TbfRY2R8Y"]["last_played"]


def test_list_cache_action_validates_sort(monkeypatch, tmp_path):
    _use_data(monkeypatch, tmp_path)
    _touch(tmp_path, "58TbfRY2R8Y.dfpwm", b"z")

    page = asyncio.run(
        Actions.list_cache(
            {"action": "list_cache", "sort": "title", "search": "58"},
            None,
            None,
        )
    )
    assert page["action"] == "list_cache"
    assert page["entries"][0]["title"] == "58TbfRY2R8Y"

    error = asyncio.run(
        Actions.list_cache({"action": "list_cache", "sort": "size"}, None, None)
    )
    assert error["action"] == "error"
