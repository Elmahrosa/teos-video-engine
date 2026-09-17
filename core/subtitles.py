"""TEOS Sovereign Video Engine — Local Subtitle Generator.

Creates perfectly timed .srt subtitles from the generated audio using an
on-device Whisper transcription — zero external transcription APIs.
"""

import asyncio
import os
import shutil
import time
from pathlib import Path

import imageio_ffmpeg

from core.config import load_config


def _ensure_ffmpeg_on_path() -> None:
    """Whisper shells out to `ffmpeg`. Reuse the binary bundled with
    imageio-ffmpeg so the forge is self-sufficient."""
    if shutil.which("ffmpeg"):
        return
    try:
        ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 — ffmpeg may be provided by the OS
        return
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def _srt_timestamp(seconds: float) -> str:
    milli = int(round(seconds * 1000))
    hours, rem = divmod(milli, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(segments: list, output_srt_path: str) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = segment.get("start", 0.0)
        end = segment.get("end", start)
        text = segment.get("text", "").strip().replace("\n", " ")
        if not text:
            continue
        lines.append(f"{index}\n")
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n")
        lines.append(f"{text}\n\n")
    output = Path(output_srt_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(lines), encoding="utf-8")
    return str(output)


async def generate_subtitles(audio_path: str, output_srt_path: str) -> str:
    """Transcribe the audio locally and write an .srt subtitle file.

    Returns the path to the generated subtitle file.
    """
    _ensure_ffmpeg_on_path()

    cfg = load_config()
    gateway = cfg["gateway"]
    model_name = gateway.get("whisper_model", "tiny")
    language = gateway.get("whisper_language", "en")

    # Deferred import: whisper pulls torch, so fail loudly only when used.
    import whisper  # noqa: PLC0415

    model = await asyncio.to_thread(whisper.load_model, model_name, device="cpu")
    result = await asyncio.to_thread(
        model.transcribe,
        audio_path,
        language=language,
        fp16=False,
        verbose=False,
    )
    return write_srt(result["segments"], output_srt_path)