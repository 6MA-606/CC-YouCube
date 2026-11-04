"""FFmpeg DFPWM conversion used by the audio pipeline."""

import asyncio
import math
import struct
import wave
from os import remove
from os.path import exists, getsize, join
from tempfile import TemporaryDirectory

from yc_download import download_audio
from yc_utils import DATA_FOLDER, create_data_folder_if_not_present, get_audio_name


class _FakeSocket:
    async def send(self, _payload):
        return None


def _write_tone(path: str) -> None:
    sample_rate = 48000
    frames = [
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
        for index in range(sample_rate // 5)
    ]
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(frames))


def test_ffmpeg_converts_wav_to_dfpwm():
    media_id = "pytesttone"
    output = join(DATA_FOLDER, get_audio_name(media_id))
    create_data_folder_if_not_present()
    if exists(output):
        remove(output)

    async def convert():
        with TemporaryDirectory(prefix="youcube-tone-") as temp_dir:
            _write_tone(join(temp_dir, "tone.wav"))
            download_audio(temp_dir, media_id, _FakeSocket(), asyncio.get_running_loop())

    asyncio.run(convert())
    try:
        assert exists(output)
        assert getsize(output) > 0
    finally:
        if exists(output):
            remove(output)
