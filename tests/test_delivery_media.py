import asyncio
import io
import json
import math
import struct
import time
import wave
from pathlib import Path

import httpx
import pytest
from app.db.models import ModelConfig, Project, Provider, RoleAssignment, SlideSpecRecord
from app.db.session import SessionLocal
from app.delivery_media import ffmpeg as media
from app.delivery_media.narration import (
    MIN_SLIDE_SECONDS,
    deck_narration,
    estimate_speech_seconds,
    fallback_narration,
    slide_narration,
)
from app.delivery_media.subtitles import render_srt, segment_cues, split_cue_text
from app.delivery_media.video import build_narrated_video
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError
from PIL import Image

FFMPEG = media.find_ffmpeg()
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")


def _slide(position, **extra):
    return {
        "id": f"s{position}",
        "position": position,
        "role": "content",
        "message": f"第{position}页结论",
        "content": {"title": f"标题{position}", "bullets": ["要点甲", "要点乙"]},
        **extra,
    }


def _wav(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000)))
            for i in range(int(16000 * seconds))
        )
        handle.writeframes(frames)
    return buffer.getvalue()


def _render(root: Path, positions) -> Path:
    slides_root = root / "slides" / "rendered" / "slides"
    for position in positions:
        folder = slides_root / str(position)
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), (40 * position, 90, 160)).save(folder / "editorial.png")
        (folder / "current.json").write_text(json.dumps({"variant": "editorial"}), encoding="utf-8")
    return slides_root


def test_narration_prefers_speaker_notes_then_talking_points_then_fallback():
    noted = slide_narration(_slide(1, speakerIntent={"narration": "请关注增长来源"}))
    assert noted.source == "speaker-notes"
    assert noted.text == "请关注增长来源。"
    pointed = slide_narration(_slide(2, speakerIntent={"talkingPoints": ["市场", "成本"]}))
    assert (pointed.source, pointed.text) == ("talking-points", "市场；成本。")
    generated = slide_narration(_slide(3))
    assert generated.source == "generated"
    assert generated.text == "这一页介绍标题3。第3页结论。重点包括：要点甲；要点乙。"
    assert generated.text == slide_narration(_slide(3)).text
    english = fallback_narration(_slide(4), "en-US")
    assert english.startswith("This slide covers 标题4.")
    ordered = deck_narration([_slide(2), _slide(1)])
    assert [item.position for item in ordered] == [1, 2]


def test_speech_duration_estimate_scales_with_text_and_has_floor():
    assert estimate_speech_seconds("") == MIN_SLIDE_SECONDS
    assert estimate_speech_seconds("你好") == MIN_SLIDE_SECONDS
    assert estimate_speech_seconds("这是一段较长的讲解文本" * 10) > 20
    assert estimate_speech_seconds("one two three four five six seven eight nine ten " * 3) > 10


def test_subtitles_split_and_render_srt():
    chunks = split_cue_text("第一句话。第二句话比较长，需要在逗号处断开以便阅读，并且继续描述更多的细节内容。")
    assert chunks[0] == "第一句话。"
    assert all(len(chunk) <= 24 for chunk in chunks)
    cues = segment_cues("第一句。第二句。", 2.0, 4.0)
    assert cues[0].start == 2.0 and cues[-1].end == 6.0
    srt = render_srt(cues)
    assert srt.startswith("1\n00:00:02,000 --> 00:00:04,000\n第一句。\n")
    assert "2\n00:00:04,000 --> 00:00:06,000\n第二句。" in srt


def test_ffmpeg_command_construction(tmp_path):
    image, audio, out = tmp_path / "a.png", tmp_path / "a.mp3", tmp_path / "seg.mp4"
    with_audio = media.segment_command("ffmpeg", image, out, 5.25, audio)
    assert with_audio[:5] == ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    assert ["-loop", "1"] == with_audio[5:7]
    assert with_audio[with_audio.index("-t") + 1] == "5.250"
    assert str(audio) in with_audio and "anullsrc" not in " ".join(with_audio)
    assert "scale=1920:1080" in with_audio[with_audio.index("-vf") + 1]
    assert with_audio[-1] == str(out)
    silent = media.segment_command("ffmpeg", image, out, 3, None)
    assert "lavfi" in silent and any(item.startswith("anullsrc=") for item in silent)
    assert silent[silent.index("-c:v") + 1] == "libx264"

    listing = media.concat_list([tmp_path / "it's.mp4"])
    assert listing.startswith("file '") and "'\\''" in listing
    plain = media.concat_command("ffmpeg", tmp_path / "list.txt", out)
    assert ["-f", "concat", "-safe", "0"] == plain[5:9] and "-c" in plain
    subbed = media.concat_command("ffmpeg", tmp_path / "list.txt", out, tmp_path / "a.srt", "eng")
    assert subbed[subbed.index("-c:s") + 1] == "mov_text"
    assert "language=eng" in subbed
    assert media.parse_duration("  Duration: 00:01:02.50, start: 0") == pytest.approx(62.5)
    assert media.parse_duration("no duration") is None


def test_find_ffmpeg_prefers_configured_path(tmp_path, monkeypatch):
    fake = tmp_path / "ffmpeg-custom"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("YINGZHANG_FFMPEG", str(fake))
    assert media.find_ffmpeg() == str(fake)
    monkeypatch.setenv("YINGZHANG_FFMPEG", str(tmp_path / "missing"))
    assert media.find_ffmpeg() is None
    monkeypatch.delenv("YINGZHANG_FFMPEG")
    monkeypatch.setattr(media.settings, "ffmpeg", None)
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    assert media.find_ffmpeg() == "/usr/bin/ffmpeg"


REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_async_client(monkeypatch, handler):
    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr("app.providers.openai_compatible.httpx.AsyncClient", factory)


def test_speech_posts_openai_compatible_payload(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, content=b"ID3-audio", headers={"content-type": "audio/mpeg"})

    _mock_async_client(monkeypatch, handler)
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", "sk-test-123456", {}, 5)
    audio = asyncio.run(client.speech("tts-1", "你好", voice="nova", speed=1.1))
    assert audio == b"ID3-audio"
    assert seen["url"] == "http://127.0.0.1:9/v1/audio/speech"
    assert seen["auth"] == "Bearer sk-test-123456"
    assert seen["json"] == {
        "model": "tts-1", "input": "你好", "voice": "nova", "response_format": "mp3", "speed": 1.1,
    }


def test_speech_reports_provider_errors_without_leaking_keys(monkeypatch):
    def handler(_request):
        return httpx.Response(401, json={"error": {"message": "bad key sk-test-123456"}})

    _mock_async_client(monkeypatch, handler)
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", "sk-test-123456", {}, 5)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(client.speech("tts-1", "你好"))
    assert "401" in str(caught.value) and "sk-test-123456" not in str(caught.value)

    _mock_async_client(monkeypatch, lambda _r: httpx.Response(200, json={"error": "quota"}))
    with pytest.raises(ProviderError, match="quota"):
        asyncio.run(client.speech("tts-1", "你好"))


@needs_ffmpeg
def test_build_video_mixes_tts_audio_and_silent_fallback(tmp_path):
    rendered = _render(tmp_path, [1, 2])
    calls = []

    async def synthesize(text):
        calls.append(text)
        if len(calls) == 2:
            raise ProviderError("语音服务暂时不可用")
        return _wav(1.0)

    build = asyncio.run(build_narrated_video(
        [_slide(2), _slide(1, speakerIntent={"narration": "开场说明。"})],
        rendered, tmp_path / "work", tmp_path / "out" / "deck.mp4",
        ffmpeg=FFMPEG, synthesize=synthesize, audio_format="wav",
    ))
    assert build.video.is_file() and build.video.stat().st_size > 1000
    report = build.report()
    assert [item["audio"] for item in report["segments"]] == ["tts", "silent"]
    assert report["segments"][1]["ttsError"] == "语音服务暂时不可用"
    assert report["segments"][0]["duration"] == pytest.approx(1.6, abs=0.15)
    import subprocess

    banner = subprocess.run(
        media.probe_command(FFMPEG, build.video), capture_output=True, text=True, check=False
    ).stderr
    assert "Subtitle: mov_text" in banner and "Audio: aac" in banner and "1920x1080" in banner
    measured = media.probe_duration(FFMPEG, build.video)
    assert measured == pytest.approx(report["durationSeconds"], abs=0.5)
    srt = build.subtitles.read_text(encoding="utf-8")
    assert "开场说明。" in srt and "这一页介绍标题2。" in srt


def test_video_job_requires_ffmpeg(client, monkeypatch):
    project = client.post("/api/v1/projects", json={"name": "讲解视频"}).json()
    monkeypatch.setattr("app.api.delivery_routes.ensure_current_preview", lambda *_: None)
    monkeypatch.setattr("app.api.delivery_routes.find_ffmpeg", lambda: None)
    response = client.post(f"/api/v1/projects/{project['id']}/jobs/video", json={})
    assert response.status_code == 409
    assert "ffmpeg" in response.json()["detail"]


@needs_ffmpeg
def test_video_job_exports_registered_mp4_with_routed_tts(client, monkeypatch):
    project = client.post("/api/v1/projects", json={"name": "讲解视频"}).json()
    with SessionLocal() as db:
        root = Path(db.get(Project, project["id"]).artifact_path)
        for position in (1, 2):
            db.add(SlideSpecRecord(
                id=f"{project['id'][:8]}-{position}", project_id=project["id"],
                position=position, spec=_slide(position, id=f"{project['id'][:8]}-{position}"),
            ))
        provider = Provider(name="local-tts", base_url="http://127.0.0.1:9/v1")
        db.add(provider)
        db.flush()
        model = ModelConfig(provider_id=provider.id, model_id="tts-mini", capabilities=["tts"])
        db.add(model)
        db.commit()
        model_id = model.id
    _render(root, [1, 2])
    assert client.put("/api/v1/model-routing", json={"role": "tts", "model_config_id": model_id}).status_code == 200
    spoken = []

    async def fake_speech(self, model, text, **kwargs):
        spoken.append((model, kwargs.get("voice"), text))
        return _wav(0.5)

    monkeypatch.setattr(OpenAICompatibleClient, "speech", fake_speech)
    monkeypatch.setattr("app.api.delivery_routes.ensure_current_preview", lambda *_: None)
    response = client.post(
        f"/api/v1/projects/{project['id']}/jobs/video",
        json={"voice": "nova", "audio_format": "wav"},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    deadline = time.time() + 60
    while job["status"] not in {"completed", "failed", "cancelled"} and time.time() < deadline:
        time.sleep(0.2)
        job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "completed", job
    result = job["checkpoint"]["result"]
    assert result["ttsSlides"] == 2 and result["silentSlides"] == 0
    assert [item[:2] for item in spoken] == [("tts-mini", "nova"), ("tts-mini", "nova")]
    video = client.get(f"/api/v1/projects/{project['id']}/export/video")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    subtitles = client.get(f"/api/v1/projects/{project['id']}/export/video?subtitles=true")
    assert subtitles.status_code == 200 and "-->" in subtitles.text
    assert (root / "exports" / "presentation.mp4").is_file()
    assert not (root / "exports" / "video-work").exists() or not any((root / "exports" / "video-work").iterdir())


def test_tts_role_requires_tts_capability(client):
    with SessionLocal() as db:
        provider = Provider(name="chat-only", base_url="http://127.0.0.1:9/v1")
        db.add(provider)
        db.flush()
        model = ModelConfig(provider_id=provider.id, model_id="chat", capabilities=["chat"])
        db.add(model)
        db.commit()
        model_id = model.id
        assert db.get(RoleAssignment, "tts") is None
    response = client.put("/api/v1/model-routing", json={"role": "tts", "model_config_id": model_id})
    assert response.status_code == 422
