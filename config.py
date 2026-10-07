from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    max_bot_token: str = Field(alias="MAX_BOT_TOKEN")

    brave_path: str = Field(alias="BRAVE_PATH")
    bot_profile: Path = Field(alias="BOT_PROFILE")
    screenshot_path: Path = Field(alias="SCREENSHOT_PATH")
    gpt_timeout: int = Field(alias="GPT_TIMEOUT")
    gpt_downloads: Path = Field(
        default=Path("runtime/gpt-downloads"),
        alias="GPT_DOWNLOADS",
    )
    gpt_dialogs: Path = Field(
        default=Path("runtime/gpt-dialogs.json"),
        alias="GPT_DIALOGS",
    )

    taxi_profile: Path = Field(
        default=Path("runtime/yandex-taxi-profile"),
        alias="TAXI_PROFILE",
    )
    taxi_address_book: Path = Field(
        default=Path("runtime/taxi-addresses.json"),
        alias="TAXI_ADDRESS_BOOK",
    )
    taxi_screenshot: Path = Field(
        default=Path("runtime/taxi-screenshot.png"),
        alias="TAXI_SCREENSHOT",
    )
    taxi_url: str = Field(
        default="https://taxi.yandex.ru/",
        alias="TAXI_URL",
    )
    taxi_mobile_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        alias="TAXI_MOBILE_USER_AGENT",
    )

    media_dir: Path = Field(default=Path("runtime/media"), alias="MEDIA_DIR")
    max_extracted_files: int = Field(default=200, alias="MAX_EXTRACTED_FILES")
    max_extracted_bytes: int = Field(default=512 * 1024 * 1024, alias="MAX_EXTRACTED_BYTES")
    whisper_model: str = Field(default="small", alias="WHISPER_MODEL")

    abie_repo_url: str = Field(
        default="https://github.com/kalentivan/abie.git",
        alias="ABIE_REPO_URL",
    )
    abie_snapshot_dir: Path = Field(
        default=Path("runtime/snapshots"),
        alias="ABIE_SNAPSHOT_DIR",
    )

    # Direct HTTP access to the running ABIE installation.
    abie_api_url: str = Field(default="", alias="ABIE_API_URL")
    abie_api_timeout: int = Field(default=120, alias="ABIE_API_TIMEOUT")
    abie_openapi_path: str = Field(default="", alias="ABIE_OPENAPI_PATH")
    abie_http_output_dir: Path = Field(
        default=Path("runtime/abie-http"),
        alias="ABIE_HTTP_OUTPUT_DIR",
    )
    abie_max_response_bytes: int = Field(
        default=256 * 1024 * 1024,
        alias="ABIE_MAX_RESPONSE_BYTES",
    )
    abie_max_request_chain: int = Field(default=100, alias="ABIE_MAX_REQUEST_CHAIN")

    # Loki may be exposed separately from the ABIE API.
    loki_url: str = Field(default="", alias="LOKI_URL")
    loki_timeout: int = Field(default=120, alias="LOKI_TIMEOUT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
