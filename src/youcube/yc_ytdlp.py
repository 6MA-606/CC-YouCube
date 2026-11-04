#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
yt-dlp settings and messages for YouTube bot checks.

Environment variables, all optional:

- YTDLP_COOKIES: path to a Netscape cookies.txt file
- YTDLP_PLAYER_CLIENT: comma-separated YouTube player clients
- YTDLP_PO_TOKEN: one po_token value in yt-dlp's client.context+TOKEN form
- YTDLP_EXTRACTOR_ARGS: raw yt-dlp extractor args, for example
  ``youtube:player_client=default,mweb;po_token=mweb.gvs+TOKEN``
- YTDLP_EXTRA_ARGS: extra yt-dlp command-line arguments
- YTDLP_JS_RUNTIMES: comma-separated runtimes (``node`` or ``deno:/usr/bin/deno``).
  ``none`` disables them. When unset, the first runtime on PATH is used.
- YTDLP_AUDIO_FORMAT / YTDLP_VIDEO_FORMAT: override the yt-dlp format selector
"""

# Built-in modules
from os import getenv
from os.path import isfile
from shlex import split as shlex_split
from shutil import which

# Local modules
from yc_logging import logger

_JS_RUNTIME_NAMES = ("deno", "node", "bun", "quickjs")
_PROTECTED_YDL_KEYS = frozenset({"outtmpl", "progress_hooks", "logger"})
_AUTH_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "login required",
    "please sign in",
    "use --cookies",
    "cookies-from-browser",
    "po token",
    "confirm your age",
    "sign in to view",
)


def _diff_ydl_opts(argv: list) -> dict:
    """Return yt-dlp options that differ from a bare ``--ignore-config`` parse."""
    # Imported lazily so logging setup does not depend on yt-dlp import time.
    # pylint: disable=import-outside-toplevel
    from yt_dlp import parse_options

    baseline = parse_options(["--ignore-config"]).ydl_opts
    parsed = parse_options(["--ignore-config", *argv]).ydl_opts
    diff = {}
    for key, value in parsed.items():
        if key in _PROTECTED_YDL_KEYS:
            continue
        if baseline.get(key) != value:
            diff[key] = value
    return diff


def _merge_extractor_args(left: dict, right: dict) -> dict:
    merged = {}
    for source in (left, right):
        for ie_key, args in source.items():
            slot = merged.setdefault(ie_key, {})
            if isinstance(args, dict) and isinstance(slot, dict):
                slot.update(args)
            else:
                merged[ie_key] = args
    return merged


def js_runtimes_from_env() -> dict:
    """Build the ``js_runtimes`` option from the environment or PATH."""
    raw = getenv("YTDLP_JS_RUNTIMES", "").strip()
    if raw.lower() in {"none", "off", "disable"}:
        return {}

    specs = []
    if raw:
        specs = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        for name in _JS_RUNTIME_NAMES:
            path = which(name)
            if path:
                specs.append(f"{name}:{path}")
                break

    runtimes = {}
    for spec in specs:
        name, _separator, path = spec.partition(":")
        runtimes[name.strip().lower()] = {"path": path or None}
    return runtimes


def apply_yt_dlp_options(options: dict) -> dict:  # pylint: disable=too-many-branches
    """Add cookies, extractor arguments, and a JavaScript runtime."""
    opts = dict(options)
    extractor_args = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in (opts.get("extractor_args") or {}).items()
    }

    player_client = getenv("YTDLP_PLAYER_CLIENT", "").strip()
    po_token = getenv("YTDLP_PO_TOKEN", "").strip()
    youtube_args = dict(extractor_args.get("youtube") or {})
    if player_client:
        youtube_args["player_client"] = [
            part.strip() for part in player_client.split(",") if part.strip()
        ]
    if po_token:
        youtube_args["po_token"] = [po_token]
    if youtube_args:
        extractor_args["youtube"] = youtube_args

    raw_extractor = getenv("YTDLP_EXTRACTOR_ARGS", "").strip()
    if raw_extractor:
        try:
            parsed = _diff_ydl_opts(["--extractor-args", raw_extractor])
        except SystemExit:
            logger.error(
                "YTDLP_EXTRACTOR_ARGS was rejected by yt-dlp: %s", raw_extractor
            )
        else:
            extractor_args = _merge_extractor_args(
                extractor_args, parsed.pop("extractor_args", {}) or {}
            )
            opts.update(parsed)

    extra_args = getenv("YTDLP_EXTRA_ARGS", "").strip()
    if extra_args:
        try:
            parsed = _diff_ydl_opts(shlex_split(extra_args))
        except SystemExit:
            logger.error("YTDLP_EXTRA_ARGS was rejected by yt-dlp: %s", extra_args)
        except ValueError as exc:
            logger.error("Could not parse YTDLP_EXTRA_ARGS: %s", exc)
        else:
            extractor_args = _merge_extractor_args(
                extractor_args, parsed.pop("extractor_args", {}) or {}
            )
            opts.update(parsed)

    if extractor_args:
        opts["extractor_args"] = extractor_args

    cookies = getenv("YTDLP_COOKIES", "").strip()
    if cookies:
        if isfile(cookies):
            opts["cookiefile"] = cookies
        else:
            logger.error(
                "YTDLP_COOKIES is set but the file was not found: %s", cookies
            )

    if not opts.get("js_runtimes"):
        runtimes = js_runtimes_from_env()
        if runtimes:
            opts["js_runtimes"] = runtimes

    return opts


def looks_like_youtube_auth_block(message: str) -> bool:
    """Return True when yt-dlp output looks like a YouTube sign-in wall."""
    lowered = message.lower()
    if any(marker in lowered for marker in _AUTH_MARKERS):
        return True
    return "403" in lowered and "youtube" in lowered


def explain_download_error(exc: BaseException) -> str:
    """Log a direct hint for sign-in walls and return a client-safe message."""
    text = str(exc)
    if looks_like_youtube_auth_block(text):
        logger.error(
            "YouTube refused the request and may be asking for sign-in or a bot check. "
            "Export a Netscape cookies.txt from a logged-in browser and set YTDLP_COOKIES "
            "to that file, or set YTDLP_PO_TOKEN, YTDLP_PLAYER_CLIENT, or "
            "YTDLP_EXTRACTOR_ARGS. Original error: %s",
            text,
        )
        return (
            "YouTube asked for sign-in or a bot check. "
            "The server needs cookies or a PO token."
        )

    logger.exception("yt-dlp failed")
    return "Failed to download media"


def log_ytdlp_configuration() -> None:
    """Log which optional yt-dlp features are active, without secret values."""
    cookies = getenv("YTDLP_COOKIES", "").strip()
    if cookies:
        if isfile(cookies):
            logger.info("yt-dlp cookies file configured")
        else:
            logger.error(
                "YTDLP_COOKIES is set but the file was not found: %s", cookies
            )
    else:
        logger.info("yt-dlp cookies file is not configured")

    if any(
        getenv(name, "").strip()
        for name in (
            "YTDLP_PLAYER_CLIENT",
            "YTDLP_PO_TOKEN",
            "YTDLP_EXTRACTOR_ARGS",
            "YTDLP_EXTRA_ARGS",
        )
    ):
        logger.info("Custom yt-dlp extractor options are enabled")

    runtimes = js_runtimes_from_env()
    if runtimes:
        logger.info(
            "yt-dlp JavaScript runtime: %s", ", ".join(sorted(runtimes))
        )
    else:
        logger.warning(
            "No JavaScript runtime found for yt-dlp. "
            "YouTube downloads may fail until Node.js or Deno is installed."
        )
