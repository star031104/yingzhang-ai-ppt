from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# YINGZHANG_ is the documented prefix; SLIDEFORGE_ stays accepted for existing installs.
ENV_PREFIX = "YINGZHANG_"
LEGACY_ENV_PREFIX = "SLIDEFORGE_"


class Settings(BaseSettings):
    """Runtime settings.

    Precedence (highest first): constructor arguments, process ``YINGZHANG_*``,
    process ``SLIDEFORGE_*``, ``.env`` ``YINGZHANG_*``, ``.env`` ``SLIDEFORGE_*``.
    Within the same source the new prefix always wins.
    """

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./runtime/data/yingzhang.db"
    migrate_on_startup: bool = True
    artifact_root: Path = Path("./runtime/artifacts")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    vault_key: str | None = None
    request_timeout_seconds: float = 15.0
    web_dist_root: Path = Path("./apps/web/dist")
    public_test_mode: bool = False
    public_test_password: str | None = None
    public_admin_password: str | None = None
    public_session_secret: str | None = None
    public_session_hours: int = 12
    public_rate_limit_per_minute: int = 180
    public_generation_limit_per_10_minutes: int = 12
    public_upload_limit_mb: int = 25
    trusted_proxy_ips: str = ""
    render_concurrency: int = 2
    max_concurrent_jobs: int = Field(default=2, ge=1, le=16)
    max_queued_jobs: int = Field(default=6, ge=0, le=64)
    local_only_mode: bool = False
    private_accounts_mode: bool = False
    private_cookie_secure: bool = False
    office_renderer: str = "auto"
    office_executable: str | None = None
    optional_image_wait_seconds: float = 45
    ocr_executable: str | None = None
    ocr_languages: str = "chi_sim+eng"
    ocr_max_pages: int = 20
    sqlite_busy_timeout_ms: int = Field(default=15000, ge=1000, le=120000)
    ffmpeg: str | None = None
    tts_voice: str = "alloy"
    tts_format: str = "mp3"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        legacy_env = EnvSettingsSource(settings_cls, env_prefix=LEGACY_ENV_PREFIX)
        legacy_dotenv = DotEnvSettingsSource(settings_cls, env_prefix=LEGACY_ENV_PREFIX)
        return (
            init_settings,
            env_settings,
            legacy_env,
            dotenv_settings,
            legacy_dotenv,
            file_secret_settings,
        )

    @property
    def cors_origin_list(self):
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def trusted_proxy_ip_list(self):
        return [x.strip() for x in self.trusted_proxy_ips.split(",") if x.strip()]


settings = Settings()
