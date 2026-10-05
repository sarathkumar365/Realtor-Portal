"""Environment-backed configuration. The only module that reads os.environ."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    token_secret: str = ""
    session_ms: int = 7 * 24 * 60 * 60 * 1000

    exec_url: str = ""
    exec_timeout_s: float = 30.0

    allowed_origins: str = "http://localhost:4600,http://localhost:4599"
    allowed_origin_regex: str = ""

    openrouter_api_key: str = ""
    llm_model: str = "google/gemini-2.5-flash"
    llm_max_tokens: int = 1500

    database_url: str = ""

    chat_per_hour: int = 60
    login_per_hour: int = 20
    doctor_per_hour: int = 30

    project_source: str = "exec"

    @property
    def origins(self) -> list[str]:
        """The allowlist, split and cleaned."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def auth_ready(self) -> bool:
        return bool(self.token_secret)

    @property
    def portal_ready(self) -> bool:
        return bool(self.exec_url)


def load() -> Settings:
    return Settings()
