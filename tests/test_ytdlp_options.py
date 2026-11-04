"""yt-dlp option builder."""

from yc_ytdlp import (
    apply_yt_dlp_options,
    explain_download_error,
    looks_like_youtube_auth_block,
)


def test_player_client_po_token_and_extractor_override(monkeypatch):
    monkeypatch.setenv("YTDLP_PLAYER_CLIENT", "android")
    monkeypatch.setenv("YTDLP_PO_TOKEN", "mweb.gvs+abc")
    monkeypatch.setenv("YTDLP_EXTRACTOR_ARGS", "youtube:player_client=web,mweb")
    monkeypatch.setenv("YTDLP_JS_RUNTIMES", "none")
    monkeypatch.delenv("YTDLP_EXTRA_ARGS", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES", raising=False)

    options = apply_yt_dlp_options({})
    youtube = options["extractor_args"]["youtube"]
    assert youtube["player_client"] == ["web", "mweb"]
    assert youtube["po_token"] == ["mweb.gvs+abc"]
    assert "js_runtimes" not in options


def test_extra_args_and_cookies(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIES", str(cookies))
    monkeypatch.setenv("YTDLP_EXTRA_ARGS", "--retries 4 --no-playlist")
    monkeypatch.setenv("YTDLP_JS_RUNTIMES", "node:/usr/bin/node")
    monkeypatch.delenv("YTDLP_PLAYER_CLIENT", raising=False)
    monkeypatch.delenv("YTDLP_PO_TOKEN", raising=False)
    monkeypatch.delenv("YTDLP_EXTRACTOR_ARGS", raising=False)

    options = apply_yt_dlp_options({"outtmpl": "/tmp/keep", "logger": object()})
    assert options["retries"] == 4
    assert options["noplaylist"] is True
    assert options["cookiefile"] == str(cookies)
    assert options["outtmpl"] == "/tmp/keep"
    assert options["js_runtimes"]["node"]["path"] == "/usr/bin/node"


def test_missing_cookie_file_is_not_passed(monkeypatch):
    monkeypatch.setenv("YTDLP_COOKIES", "/no/such/cookies.txt")
    monkeypatch.setenv("YTDLP_JS_RUNTIMES", "none")
    monkeypatch.delenv("YTDLP_EXTRA_ARGS", raising=False)
    monkeypatch.delenv("YTDLP_EXTRACTOR_ARGS", raising=False)
    monkeypatch.delenv("YTDLP_PLAYER_CLIENT", raising=False)
    monkeypatch.delenv("YTDLP_PO_TOKEN", raising=False)
    options = apply_yt_dlp_options({})
    assert "cookiefile" not in options


def test_sign_in_message_detection():
    message = "Sign in to confirm you're not a bot. Use --cookies-from-browser"
    assert looks_like_youtube_auth_block(message) is True
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        client_message = explain_download_error(exc)
    assert "sign-in" in client_message
    assert "cookies" in client_message
