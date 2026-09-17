"""TEOS Sovereign Video Engine — Video Assembler.

Renders the final short-form MP4 entirely from sovereign assets:
TEOS-branded solid background + generated audio + burned-in local subtitles.
No stock footage APIs — everything runs on-device.
"""

from pathlib import Path

from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, TextClip

from core.config import load_config


def _srt_entries(srt_path: str) -> list:
    entries: list = []
    text = Path(srt_path).read_text(encoding="utf-8")
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_s, end_s = lines[1].split("-->")
        entries.append(
            {
                "start": _parse_timestamp(start_s.strip()),
                "end": _parse_timestamp(end_s.strip()),
                "text": " ".join(lines[2:]).strip(),
            }
        )
    return entries


def _parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _resolve_font(configured: str) -> str | None:
    if configured and Path(configured).exists():
        return configured
    candidates = (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _subtitle_clips(entries: list, size: tuple, font: str | None, fps: int) -> list:
    width, height = size
    box_width = int(width * 0.86)
    caption_y = int(height * 0.76)
    clips = []
    for entry in entries:
        duration = max(entry["end"] - entry["start"], 0.4)
        clip = TextClip(
            font=font,
            text=entry["text"],
            font_size=int(width * 0.045),
            color="white",
            stroke_color="black",
            stroke_width=2,
            method="caption",
            size=(box_width, None),
            text_align="center",
            horizontal_align="center",
            vertical_align="center",
        )
        clip = clip.with_start(entry["start"]).with_duration(duration)
        clip = clip.with_position(("center", caption_y))
        clips.append(clip)
    return clips


def assemble_video(
    script: str,
    audio_path: str,
    srt_path: str,
    output_path: str,
) -> str:
    """Combine background, audio track and burned-in subtitles into an MP4.

    Returns the path to the rendered video file.
    """
    cfg = load_config()
    video_cfg = cfg.get("video", {})
    width = int(video_cfg.get("width", 1080))
    height = int(video_cfg.get("height", 1920))
    fps = int(video_cfg.get("fps", 30))
    bg = tuple(video_cfg.get("background", [8, 10, 22]))
    font = _resolve_font(video_cfg.get("subtitle_font", ""))

    audio = AudioFileClip(audio_path)
    duration = float(audio.duration)

    background = ColorClip(size=(width, height), color=bg, duration=duration).with_fps(fps)

    entries = _srt_entries(srt_path)
    subtitles = _subtitle_clips(entries, (width, height), font, fps)

    video = CompositeVideoClip([background] + subtitles, size=(width, height))
    video = video.with_audio(audio).with_duration(duration)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    video.close()
    audio.close()
    return str(out_path)