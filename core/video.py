"""TEOS Sovereign Video Engine — Video Assembler.

Renders the final short-form MP4 entirely from sovereign assets: a Ken Burns
sequence of media pulled from the local Sovereign Media Vault, or the
TEOS-branded solid canvas as fallback, plus generated audio and burned-in
local subtitles. No stock footage APIs — everything runs on-device.

Rendering path: a single lazy ``VideoClip`` whose frame function crops the
vault media (cv2) and blits the active pre-rendered caption directly into the
canvas via numpy — avoiding MoviePy's per-frame CompositeVideoClip blitting,
which is dramatically slower at 1080p.
"""

import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from moviepy import AudioFileClip, ColorClip, VideoClip, VideoFileClip

from core.config import load_config


def _unique_mp4_path() -> str:
    run_id = f"forge_{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:6]}"
    return str(Path("assets") / "videos" / f"{run_id}.mp4")


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


def _cover_frame(path: Path, size: tuple[int, int]) -> np.ndarray:
    """Load *path* as an RGB array cropped to cover *size* (never distorted)."""
    from PIL import Image

    image = Image.open(path).convert("RGB")
    target_width, target_height = size
    target_ratio = target_width / target_height
    src_ratio = image.width / image.height
    if src_ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        box = (
            (image.width - new_width) // 2,
            0,
            (image.width + new_width) // 2,
            image.height,
        )
    else:
        new_height = int(image.width / target_ratio)
        box = (
            0,
            (image.height - new_height) // 2,
            image.width,
            (image.height + new_height) // 2,
        )
    return np.asarray(image.crop(box).resize((target_width, target_height), Image.LANCZOS))


def _ken_burns_image(
    path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
    zoom: float,
    zoom_in: bool,
) -> VideoClip:
    """A still image given life via a slow, centered zoom (Ken Burns).

    The source is staged once at ~(1 + zoom) canvas size with cv2, then every
    frame is a centered window rescaled back to the exact canvas via cv2
    (C-speed). moviepy's own per-frame ``resized`` re-decodes the full JPEG on
    every frame and is far too slow at 1080x1920.
    """
    import cv2

    width, height = size
    big_width = int(round(width * (1.0 + max(zoom, 0.05))))
    big_height = int(round(height * (1.0 + max(zoom, 0.05))))
    big = cv2.resize(
        _cover_frame(path, size),
        (big_width, big_height),
        interpolation=cv2.INTER_LINEAR,
    )

    def make_frame(t: float) -> np.ndarray:
        progress = t / duration if duration > 0 else 1.0
        shade = progress if zoom_in else (1.0 - progress)
        scale = 1.0 + zoom * shade
        window_w = int(round(width * scale))
        window_h = int(round(height * scale))
        x0 = (big.shape[1] - window_w) // 2
        y0 = (big.shape[0] - window_h) // 2
        window = big[y0 : y0 + window_h, x0 : x0 + window_w]
        return cv2.resize(window, (width, height), interpolation=cv2.INTER_LINEAR)

    return VideoClip(make_frame).with_duration(duration).with_fps(fps)


def _clip_video_segment(
    path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
) -> VideoFileClip:
    """A vault video scaled to cover *size*, truncated to its slice duration."""
    clip = VideoFileClip(str(path), audio=False)
    scale = max(size[0] / clip.w, size[1] / clip.h)
    scale = min(scale, 2.0)
    clip = clip.resized(scale).with_fps(fps)
    if clip.duration > duration:
        clip = clip.subclipped(0, duration)
    else:
        clip = clip.with_duration(duration)
    return clip


def _background_clip(
    assets: list[str],
    duration: float,
    size: tuple[int, int],
    fps: int,
    background_color: tuple,
    slice_seconds: float,
    zoom: float,
) -> VideoClip:
    """Build the canvas: a Ken Burns vault sequence, or the brand solid color."""
    width, height = size
    if not assets:
        return ColorClip(size=(width, height), color=background_color, duration=duration).with_fps(fps)

    asset_count = len(assets)
    slice_count = max(asset_count, int(round(duration / slice_seconds)))
    share = duration / slice_count
    clips = []
    for index in range(slice_count):
        path = Path(assets[index % asset_count])
        if path.suffix.lower() == ".mp4":
            clips.append(_clip_video_segment(path, share, size, fps))
        else:
            clips.append(
                _ken_burns_image(path, share, size, fps, zoom, zoom_in=(index % 2 == 0))
            )

    def make_frame(t: float) -> np.ndarray:
        slice_index = min(int(t / share), len(clips) - 1)
        return clips[slice_index].get_frame(t - slice_index * share)

    return VideoClip(make_frame).with_duration(duration).with_fps(fps)


def _subtitle_clips(entries: list, size: tuple, font: str | None, fps: int) -> list:
    """Pre-render each burned-in caption to an RGBA image region for blitting.

    Keeps the earlier TextClip geometry (86% box width, ~4.5% canvas font,
    centered at 76% canvas height) but renders each caption once with PIL.
    Returns dicts of ``start``/``end`` plus the raster and its placement.
    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = size
    box_width = int(width * 0.86)
    caption_y = int(height * 0.76)
    font_size = int(width * 0.045)
    font_obj = ImageFont.truetype(font, font_size) if font else ImageFont.load_default()

    regions = []
    for entry in entries:
        words = entry["text"].split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if font_obj.getlength(trial) <= box_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        line_height = int(font_size * 1.35) + font_size // 4
        image = Image.new("RGBA", (box_width, line_height * len(lines)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (0, 0),
            "\n".join(lines),
            font=font_obj,
            fill=(255, 255, 255, 255),
            stroke_width=max(2, font_size // 20),
            stroke_fill=(0, 0, 0, 200),
            align="center",
            spacing=font_size // 4,
        )
        raster = np.asarray(image)
        width_crop = int(np.any(raster[:, :, 3] > 0, axis=0).sum()) or box_width
        raster = raster[:, : max(width_crop, 1)]
        regions.append(
            {
                "start": entry["start"],
                "end": entry["end"],
                "x": max((width - raster.shape[1]) // 2, 0),
                "y": caption_y,
                "raster": raster,
            }
        )
    return regions


def _blit_caption(frame: np.ndarray, region: dict) -> np.ndarray:
    """Alpha-composite one pre-rendered caption raster into *frame* in place."""
    raster = region["raster"]
    raster_h, raster_w = raster.shape[:2]
    y0, x0 = region["y"], region["x"]
    frame_h, frame_w = frame.shape[:2]
    raster_h = min(raster_h, frame_h - y0)
    raster_w = min(raster_w, frame_w - x0)
    alpha = raster[:raster_h, :raster_w, 3:4].astype(np.float32) / 255.0
    color = raster[:raster_h, :raster_w, :3].astype(np.float32)
    base = frame[y0 : y0 + raster_h, x0 : x0 + raster_w].astype(np.float32)
    frame[y0 : y0 + raster_h, x0 : x0 + raster_w] = (
        color * alpha + base * (1.0 - alpha)
    ).astype(np.uint8)
    return frame


def assemble_video(
    script: str,
    audio_path: str,
    srt_path: str,
    output_path: str | None = None,
    assets: list[str] | None = None,
) -> str:
    """Combine canvas, audio track and burned-in subtitles into an MP4.

    *assets* is an optional list of sovereign vault media paths. When present,
    the canvas becomes a Ken Burns sequence of those images/clips filling the
    audio duration; otherwise the TEOS-branded solid background is used. The
    burned-in subtitles ride on top of whichever canvas is chosen.

    *output_path* is optional: when omitted, a unique per-render filename is
    generated so concurrent requests never overwrite each other.

    Returns the path to the rendered video file.
    """
    cfg = load_config()
    video_cfg = cfg.get("video", {})
    width = int(video_cfg.get("width", 1080))
    height = int(video_cfg.get("height", 1920))
    fps = int(video_cfg.get("fps", 30))
    bg = tuple(video_cfg.get("background", [8, 10, 22]))
    font = _resolve_font(video_cfg.get("subtitle_font", ""))

    vault_cfg = cfg.get("vault", {})
    slice_seconds = float(vault_cfg.get("slice_seconds", 6.0))
    zoom = float(vault_cfg.get("zoom", 0.12))

    encoder_preset = video_cfg.get("encoder_preset", "veryfast")
    crf = int(video_cfg.get("crf", 28))

    audio = AudioFileClip(audio_path)
    duration = float(audio.duration)

    background = _background_clip(
        assets or [],
        duration,
        (width, height),
        fps,
        bg,
        slice_seconds,
        zoom,
    )

    entries = _srt_entries(srt_path)
    captions = _subtitle_clips(entries, (width, height), font, fps)

    def make_frame(t: float) -> np.ndarray:
        frame = background.get_frame(t)
        for region in captions:
            if region["start"] <= t < region["end"]:
                return _blit_caption(frame, region)
        return frame

    video = VideoClip(make_frame).with_fps(fps).with_duration(duration)
    video = video.with_audio(audio)

    out_path = Path(output_path) if output_path else Path(_unique_mp4_path())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset=encoder_preset,
        ffmpeg_params=["-crf", str(crf)],
        logger=None,
    )
    video.close()
    audio.close()
    return str(out_path)