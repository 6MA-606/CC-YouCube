#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Download Functionality of YC
"""

# Built-in modules
from asyncio import run_coroutine_threadsafe
from os import getenv, listdir
from os.path import abspath, dirname, join
from tempfile import TemporaryDirectory

# Local modules
from yc_colours import RESET, Foreground
from yc_logging import NO_COLOR, YTDLPLogger, logger
from yc_magic import run_with_live_output
from yc_spotify import SpotifyURLProcessor
from yc_utils import (
    cap_width_and_height,
    create_data_folder_if_not_present,
    dump_json,
    get_audio_name,
    get_video_name,
    is_audio_already_downloaded,
    is_video_already_downloaded,
    remove_ansi_escape_codes,
    remove_whitespace,
)
from yc_library import download_url_for_cache, record_playback, serve_cached_request
from yc_ytdlp import apply_yt_dlp_options, explain_download_error

# pip modules
from sanic import Websocket
from yt_dlp import YoutubeDL

# pylint settings
# pylint: disable=pointless-string-statement
# pylint: disable=fixme
# pylint: disable=too-many-locals
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=too-many-branches

DATA_FOLDER = join(dirname(abspath(__file__)), "data")
FFMPEG_PATH = getenv("FFMPEG_PATH", "ffmpeg")
SANJUUNI_PATH = getenv("SANJUUNI_PATH", "sanjuuni")
DISABLE_OPENCL = bool(getenv("DISABLE_OPENCL"))


def download_video(
    temp_dir: str, media_id: str, resp: Websocket, loop, width: int, height: int
):
    """
    Converts the downloaded video to 32vid
    """
    run_coroutine_threadsafe(
        resp.send(
            dump_json({"action": "status", "message": "Converting video to 32vid ..."})
        ),
        loop,
    )

    if NO_COLOR:
        prefix = "[Sanjuuni]"
    else:
        prefix = f"{Foreground.BRIGHT_YELLOW}[Sanjuuni]{RESET} "

    def handler(line):
        logger.debug("%s%s", prefix, line)
        run_coroutine_threadsafe(
            resp.send(dump_json({"action": "status", "message": line})), loop
        )

    command = [
        SANJUUNI_PATH,
        "--width=" + str(width),
        "--height=" + str(height),
        "-i",
        join(temp_dir, listdir(temp_dir)[0]),
        "--raw",
        "-o",
        join(DATA_FOLDER, get_video_name(media_id, width, height)),
    ]
    if DISABLE_OPENCL:
        command.append("--disable-opencl")

    returncode = run_with_live_output(command, handler)

    if returncode != 0:
        logger.warning("Sanjuuni exited with %s", returncode)
        run_coroutine_threadsafe(
            resp.send(dump_json({"action": "error", "message": "Faild to convert video!"})),
            loop,
        )


def download_audio(temp_dir: str, media_id: str, resp: Websocket, loop):
    """
    Converts the downloaded audio to dfpwm
    """
    run_coroutine_threadsafe(
        resp.send(
            dump_json({"action": "status", "message": "Converting audio to dfpwm ..."})
        ),
        loop,
    )

    if NO_COLOR:
        prefix = "[FFmpeg]"
    else:
        prefix = f"{Foreground.BRIGHT_GREEN}[FFmpeg]{RESET} "

    def handler(line):
        logger.debug("%s%s", prefix, line)
        # TODO: send message to resp

    returncode = run_with_live_output(
        [
            FFMPEG_PATH,
            "-i",
            join(temp_dir, listdir(temp_dir)[0]),
            "-f",
            "dfpwm",
            "-ar",
            "48000",
            "-ac",
            "1",
            join(DATA_FOLDER, get_audio_name(media_id)),
        ],
        handler,
    )

    if returncode != 0:
        logger.warning("FFmpeg exited with %s", returncode)
        run_coroutine_threadsafe(
            resp.send(dump_json({"action": "error", "message": "Faild to convert audio!"})),
            loop,
        )


def download(
    url: str,
    resp: Websocket,
    loop,
    width: int,
    height: int,
    spotify_url_processor: SpotifyURLProcessor,
):
    """
    Downloads and converts the media from the given URL.

    Returns the websocket response and the cache file names. Every path,
    including errors, returns that pair so the caller can unpack it.
    """

    is_video = width is not None and height is not None

    # cap height and width
    if width and height:
        width, height = cap_width_and_height(width, height)

    cached = serve_cached_request(url, width, height, is_video)
    if cached is not None:
        return cached
    url = download_url_for_cache(url)

    def my_hook(info):
        """https://github.com/yt-dlp/yt-dlp#adding-logger-and-progress-hook"""
        if info.get("status") == "downloading":
            run_coroutine_threadsafe(
                resp.send(
                    dump_json(
                        {
                            "action": "status",
                            "message": remove_ansi_escape_codes(
                                f"download {remove_whitespace(info.get('_percent_str'))} "
                                f"ETA {info.get('_eta_str')}"
                            ),
                        }
                    )
                ),
                loop,
            )

    def send_status(message: str) -> None:
        run_coroutine_threadsafe(
            resp.send(dump_json({"action": "status", "message": message})),
            loop,
        )

    # FIXME: Cleanup on Exception
    with TemporaryDirectory(prefix="youcube-") as temp_dir:
        try:
            return _download_impl(
                url,
                resp,
                loop,
                width,
                height,
                is_video,
                spotify_url_processor,
                temp_dir,
                my_hook,
                send_status,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return {"action": "error", "message": explain_download_error(exc)}, []


def _download_impl(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    url,
    resp,
    loop,
    width,
    height,
    is_video,
    spotify_url_processor,
    temp_dir,
    my_hook,
    send_status,
):
    """Run yt-dlp and the local converters. Raises on extractor failures."""
    audio_format = getenv("YTDLP_AUDIO_FORMAT", "worstaudio/worst")
    video_format = getenv("YTDLP_VIDEO_FORMAT", "worst[ext=mp4]/worst")
    yt_dl_options = apply_yt_dlp_options(
        {
            "format": video_format if is_video else audio_format,
            "outtmpl": join(temp_dir, "%(id)s.%(ext)s"),
            "default_search": "auto",
            "restrictfilenames": True,
            "extract_flat": "in_playlist",
            "progress_hooks": [my_hook],
            "logger": YTDLPLogger(),
        }
    )

    yt_dl = YoutubeDL(yt_dl_options)

    send_status("Getting resource information ...")

    playlist_videos = []

    if spotify_url_processor:
        # Spotify FIXME: The first media key is sometimes duplicated
        processed_url = spotify_url_processor.auto(url)
        if processed_url:
            if isinstance(processed_url, list):
                url = spotify_url_processor.auto(processed_url[0])
                processed_url.pop(0)
                playlist_videos = processed_url
            else:
                url = processed_url

    data = yt_dl.extract_info(url, download=False)
    if not isinstance(data, dict):
        return {"action": "error", "message": "Failed to read media information"}, []

    if data.get("extractor") == "generic":
        data["id"] = "g" + data.get("webpage_url_domain") + data.get("id")

    # Playlists return the first entry as the current media and the remaining
    # ids in playlist_videos, matching the historical client response.
    if data.get("_type") == "playlist":
        entries = [entry for entry in list(data.get("entries") or []) if entry]
        if not entries:
            return {"action": "error", "message": "Playlist is empty"}, []
        for video in entries:
            playlist_videos.append(video.get("id"))
        playlist_videos.pop(0)
        playlist_videos = [video_id for video_id in playlist_videos if video_id]
        data = entries[0]

    # Flat playlist entries omit counts, so extract the selected video fully.
    if data.get("extractor") == "youtube" and (
        data.get("view_count") is None or data.get("like_count") is None
    ):
        data = yt_dl.extract_info(data.get("id"), download=False)
        if not isinstance(data, dict):
            return {"action": "error", "message": "Failed to read media information"}, []

    media_id = data.get("id")

    if data.get("is_live"):
        return {"action": "error", "message": "Livestreams are not supported"}, []

    create_data_folder_if_not_present()

    audio_downloaded = is_audio_already_downloaded(media_id)
    video_downloaded = is_video_already_downloaded(media_id, width, height)
    needs_download = (not audio_downloaded) or (is_video and not video_downloaded)

    if needs_download:
        send_status("Downloading resource ...")
        yt_dl.process_ie_result(data, download=True)
        if not listdir(temp_dir):
            return {"action": "error", "message": "Download produced no media file"}, []

    # TODO: Thread audio & video download

    if not audio_downloaded:
        download_audio(temp_dir, media_id, resp, loop)

    if not video_downloaded and is_video:
        download_video(temp_dir, media_id, resp, loop, width, height)

    out = {
        "action": "media",
        "id": media_id,
        # "fulltitle": data.get("fulltitle"),
        "title": data.get("title"),
        "like_count": data.get("like_count"),
        "view_count": data.get("view_count"),
        # "upload_date": data.get("upload_date"),
        # "tags": data.get("tags"),
        # "description": data.get("description"),
        # "categories": data.get("categories"),
        # "channel_name": data.get("channel"),
        # "channel_id": data.get("channel_id")
    }

    # Only return playlist_videos if there are videos in playlist_videos
    if len(playlist_videos) > 0:
        out["playlist_videos"] = playlist_videos

    files = [get_audio_name(media_id)]
    if is_video:
        files.append(get_video_name(media_id, width, height))

    record_playback(
        media_id,
        title=data.get("title"),
        uploader=data.get("uploader") or data.get("channel"),
        duration=data.get("duration"),
        url=data.get("webpage_url") or url,
    )
    return out, files
