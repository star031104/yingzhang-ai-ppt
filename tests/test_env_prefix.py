from pathlib import Path

from app.config import ENV_PREFIX, LEGACY_ENV_PREFIX, Settings

FIELDS = ("RENDER_CONCURRENCY", "LOCAL_ONLY_MODE", "OCR_LANGUAGES", "FFMPEG")


def _clear(monkeypatch):
    for prefix in (ENV_PREFIX, LEGACY_ENV_PREFIX):
        for name in FIELDS:
            monkeypatch.delenv(prefix + name, raising=False)


def test_new_prefix_is_primary_and_legacy_prefix_still_works(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    assert ENV_PREFIX == "YINGZHANG_"
    assert Settings().render_concurrency == 2

    monkeypatch.setenv("SLIDEFORGE_RENDER_CONCURRENCY", "3")
    monkeypatch.setenv("SLIDEFORGE_LOCAL_ONLY_MODE", "true")
    legacy = Settings()
    assert legacy.render_concurrency == 3
    assert legacy.local_only_mode is True

    monkeypatch.setenv("YINGZHANG_RENDER_CONCURRENCY", "4")
    monkeypatch.setenv("YINGZHANG_FFMPEG", "/opt/ffmpeg/bin/ffmpeg")
    both = Settings()
    assert both.render_concurrency == 4
    assert both.local_only_mode is True
    assert both.ffmpeg == "/opt/ffmpeg/bin/ffmpeg"


def test_dotenv_accepts_both_prefixes_and_process_env_overrides_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    Path(".env").write_text(
        "SLIDEFORGE_RENDER_CONCURRENCY=3\n"
        "YINGZHANG_RENDER_CONCURRENCY=5\n"
        "SLIDEFORGE_OCR_LANGUAGES=eng\n",
        encoding="utf-8",
    )
    from_file = Settings()
    assert from_file.render_concurrency == 5
    assert from_file.ocr_languages == "eng"

    monkeypatch.setenv("SLIDEFORGE_RENDER_CONCURRENCY", "1")
    assert Settings().render_concurrency == 1
    assert Settings(render_concurrency=7).render_concurrency == 7
