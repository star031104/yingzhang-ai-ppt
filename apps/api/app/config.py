from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SLIDEFORGE_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./runtime/data/yingzhang.db"
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
    render_concurrency: int = 2
    local_only_mode: bool = False
    private_accounts_mode: bool = False
    private_cookie_secure: bool = False
    office_renderer: str = "auto"
    office_executable: str | None = None
    optional_image_wait_seconds: float = 45

    @property
    def cors_origin_list(self):
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
