"""Assemble rendered slide PNGs and narration audio into a narrated MP4."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.delivery_media import ffmpeg as media
from app.delivery_media.narration import Locale, slide_narration
from app.delivery_media.subtitles import Cue, render_srt, segment_cues
from app.delivery_media.tts import Synthesizer
from app.providers.openai_compatible import ProviderError

ProgressCallback = Callable[[int, int, str], Awaitable[None]]


@dataclass
class SegmentReport:
    position: int
    slideId: str
    narrationSource: str
    narration: str
    audio: str
    start: float
    duration: float
    ttsError: str | None = None


@dataclass
class VideoBuild:
    video: Path
    subtitles: Path | None
    durationSeconds: float
    segments: list[SegmentReport] = field(default_factory=list)

    def report(self) -> dict:
        return {
            "durationSeconds": round(self.durationSeconds, 2),
            "subtitles": str(self.subtitles) if self.subtitles else None,
            "segments": [asdict(segment) for segment in self.segments],
            "ttsSlides": sum(segment.audio == "tts" for segment in self.segments),
            "silentSlides": sum(segment.audio == "silent" for segment in self.segments),
        }


def slide_image(rendered_slides: Path, position: int) -> Path:
    """Selected candidate PNG for one slide, as written by the presentation engine."""
    root = rendered_slides / str(position)
    try:
        current = json.loads((root / "current.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"第 {position} 页尚未渲染，请先生成页面") from exc
    image = (root / f"{current.get('variant')}.png").resolve()
    if not image.is_relative_to(root.resolve()) or not image.is_file():
        raise RuntimeError(f"第 {position} 页预览图缺失，请重新生成该页")
    return image


async def build_narrated_video(
    slides: list[dict],
    rendered_slides: Path,
    work_dir: Path,
    output: Path,
    *,
    ffmpeg: str,
    synthesize: Synthesizer | None = None,
    audio_format: str = "mp3",
    locale: Locale = "zh-CN",
    subtitles: bool = True,
    on_progress: ProgressCallback | None = None,
) -> VideoBuild:
    work_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(slides, key=lambda item: item.get("position", 0))
    segments: list[Path] = []
    reports: list[SegmentReport] = []
    cues: list[Cue] = []
    cursor = 0.0
    for index, spec in enumerate(ordered, start=1):
        narration = slide_narration(spec, locale)
        position = narration.position or index
        if on_progress:
            await on_progress(index, len(ordered), f"正在制作第 {position} 页讲解片段")
        image = slide_image(rendered_slides, position)
        audio_path: Path | None = None
        duration = narration.estimated_seconds
        tts_error = None
        if synthesize and narration.text:
            try:
                data = await synthesize(narration.text)
                audio_path = work_dir / f"audio-{position:03d}.{audio_format}"
                audio_path.write_bytes(data)
                measured = await asyncio.to_thread(media.probe_duration, ffmpeg, audio_path)
                if measured:
                    duration = max(media.TAIL_SECONDS, measured) + media.TAIL_SECONDS
            except ProviderError as exc:
                # One failed page keeps a silent segment so the video stays complete.
                audio_path, tts_error = None, str(exc)[:300]
        segment = work_dir / f"segment-{position:03d}.mp4"
        command = media.segment_command(ffmpeg, image, segment, duration, audio_path)
        await asyncio.to_thread(media.run, command)
        segments.append(segment)
        cues.extend(segment_cues(narration.text, cursor, duration))
        reports.append(SegmentReport(
            position=position, slideId=narration.slide_id, narrationSource=narration.source,
            narration=narration.text, audio="tts" if audio_path else "silent",
            start=round(cursor, 3), duration=round(duration, 3), ttsError=tts_error,
        ))
        cursor += duration
    if not segments:
        raise RuntimeError("没有可制作视频的页面")
    list_file = work_dir / "segments.txt"
    list_file.write_text(media.concat_list(segments), encoding="utf-8")
    srt_path = None
    if subtitles:
        srt_path = output.with_suffix(".srt")
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        srt_path.write_text(render_srt(cues), encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    if on_progress:
        await on_progress(len(ordered), len(ordered), "正在合成完整讲解视频")
    await asyncio.to_thread(
        media.run,
        media.concat_command(
            ffmpeg, list_file, output, srt_path if cues else None,
            language="eng" if locale == "en-US" else "chi",
        ),
    )
    return VideoBuild(output, srt_path, cursor, reports)
