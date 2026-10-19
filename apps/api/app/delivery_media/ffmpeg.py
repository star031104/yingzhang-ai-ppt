"""ffmpeg discovery and command construction for narrated slide videos.

Only the ``ffmpeg`` binary is required (no ffprobe, no Python wrapper). Each slide
becomes one H.264/AAC segment with identical encoding parameters, and segments are
joined with the concat demuxer without re-encoding.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from app.config import settings

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FRAME_RATE = 30
AUDIO_RATE = 44100
TAIL_SECONDS = 0.6
_DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


class MediaToolError(RuntimeError):
    pass


def find_ffmpeg() -> str | None:
    """Locate ffmpeg via ``YINGZHANG_FFMPEG`` (or legacy prefix), then PATH."""
    configured = os.environ.get("YINGZHANG_FFMPEG") or settings.ffmpeg
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        resolved = shutil.which(configured)
        return resolved
    return shutil.which("ffmpeg")


def _video_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,"
        "setsar=1,format=yuv420p"
    )


def segment_command(
    ffmpeg: str,
    image: Path,
    output: Path,
    duration: float,
    audio: Path | None = None,
    *,
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
) -> list[str]:
    """Still image + narration (or generated silence) → one fixed-length segment."""
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(FRAME_RATE), "-i", str(image),
    ]
    if audio is not None:
        command += ["-i", str(audio)]
        audio_filter = ["-af", f"apad,aresample={AUDIO_RATE}"]
    else:
        command += [
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
        ]
        audio_filter = []
    command += [
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", _video_filter(width, height),
        *audio_filter,
        "-t", f"{duration:.3f}",
        "-r", str(FRAME_RATE),
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", str(AUDIO_RATE),
        "-movflags", "+faststart",
        str(output),
    ]
    return command


def concat_list(segments: list[Path]) -> str:
    lines = []
    for segment in segments:
        escaped = segment.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def concat_command(
    ffmpeg: str,
    list_file: Path,
    output: Path,
    subtitles: Path | None = None,
    language: str = "chi",
) -> list[str]:
    """Join identical segments losslessly; optionally attach SRT as a soft subtitle track."""
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
    ]
    if subtitles is not None:
        command += [
            "-i", str(subtitles),
            "-map", "0:v", "-map", "0:a", "-map", "1:s",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", f"language={language}",
        ]
    else:
        command += ["-c", "copy"]
    command += ["-movflags", "+faststart", str(output)]
    return command


def probe_command(ffmpeg: str, media: Path) -> list[str]:
    return [ffmpeg, "-hide_banner", "-i", str(media)]


def parse_duration(ffmpeg_output: str) -> float | None:
    match = _DURATION.search(ffmpeg_output)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def run(command: list[str], timeout: float = 600) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaToolError(f"ffmpeg 执行失败：{exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise MediaToolError("ffmpeg 执行失败：" + " ".join(detail)[:400])


def probe_duration(ffmpeg: str, media: Path) -> float | None:
    """Read container duration from ffmpeg's banner (ffmpeg exits 1 without outputs)."""
    try:
        result = subprocess.run(
            probe_command(ffmpeg, media), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_duration(result.stderr)
