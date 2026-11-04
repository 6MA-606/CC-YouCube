"""Live websocket smoke test against a single-process server."""

import base64
import json
import math
import os
import signal
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "youcube" / "data"
PYTHON = sys.executable


def _tone_wav(path: Path) -> None:
    sample_rate = 48000
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
        for index in range(sample_rate // 10)
    )
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def _start_server(port: int, token: str | None, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "NO_FAST": "1",
            "NO_COLOR": "1",
            "LOGLEVEL": "INFO",
            "DATA_CACHE_CLEANUP_INTERVAL": "0",
            "YTDLP_JS_RUNTIMES": "none",
        }
    )
    if token is None:
        env.pop("YOUCUBE_TOKEN", None)
    else:
        env["YOUCUBE_TOKEN"] = token

    log_handle = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        [PYTHON, str(ROOT / "src" / "youcube" / "youcube.py")],
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _wait_health(port: int, process: subprocess.Popen, log_path: Path) -> None:
    deadline = time.time() + 25
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(log_path.read_text(encoding="utf-8"))
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                body = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and body.get("status") == "ok":
                    return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.25)
    raise TimeoutError(log_path.read_text(encoding="utf-8"))


def _prepare_dfpwm(media_id: str) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    wav_path = DATA / f"{media_id}.wav"
    dfpwm_path = DATA / f"{media_id}.dfpwm"
    _tone_wav(wav_path)
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav_path),
            "-f",
            "dfpwm",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(dfpwm_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wav_path.unlink(missing_ok=True)
    return dfpwm_path


def test_health_handshake_chunk_and_token(tmp_path):
    media_id = "pytestchunk"
    dfpwm_path = _prepare_dfpwm(media_id)
    open_log = tmp_path / "open.log"
    locked_log = tmp_path / "locked.log"
    open_server = _start_server(8765, None, open_log)
    locked_server = _start_server(8766, "s3cret-token", locked_log)
    try:
        _wait_health(8765, open_server, open_log)
        _wait_health(8766, locked_server, locked_log)

        async def check():
            async with websockets.connect("ws://127.0.0.1:8765/") as socket:
                await socket.send(json.dumps({"action": "handshake"}))
                handshake = json.loads(await socket.recv())
                assert handshake["action"] == "handshake"
                assert handshake["api"]["version"] == "0.0.0-poc.1.0.0"
                assert handshake["capabilities"]["audio"] == ["dfpwm"]
                assert isinstance(handshake["server"]["version"], str)

                await socket.send(
                    json.dumps(
                        {"action": "get_chunk", "chunkindex": 0, "id": media_id}
                    )
                )
                chunk = json.loads(await socket.recv())
                assert chunk["action"] == "chunk"
                payload = base64.b64decode(chunk["chunk"])
                assert payload == dfpwm_path.read_bytes()[: len(payload)]
                assert payload

            async with websockets.connect("ws://127.0.0.1:8766/") as socket:
                denied = json.loads(await socket.recv())
                assert denied == {"action": "error", "message": "Unauthorized"}

            async with websockets.connect(
                "ws://127.0.0.1:8766/?token=s3cret-token"
            ) as socket:
                await socket.send(json.dumps({"action": "handshake"}))
                allowed = json.loads(await socket.recv())
                assert allowed["action"] == "handshake"

        import asyncio

        asyncio.run(check())
        locked_text = locked_log.read_text(encoding="utf-8")
        assert "s3cret-token" not in locked_text
    finally:
        _stop(open_server)
        _stop(locked_server)
        dfpwm_path.unlink(missing_ok=True)
