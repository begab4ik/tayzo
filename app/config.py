from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env — обычные настройки, tokens.env — только секреты (токены, ключи, сид-фраза).
    # Значения из tokens.env имеют приоритет. Оба файла в .gitignore.
    model_config = SettingsConfigDict(
        env_file=(".env", "tokens.env"), env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # Telegram
    bot_token: str
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")
    required_channel_id: int | None = None
    required_channel_url: str | None = None
    admin_notify_chat_id: int | None = None
    support_username: str = "support"

    # Infra
    database_url: str = "postgresql+asyncpg://tayzo:tayzo@localhost:5432/tayzo"
    redis_url: str = "redis://localhost:6379/0"

    # Click
    click_service_id: str = ""
    click_merchant_id: str = ""
    click_merchant_user_id: str = ""
    click_secret_key: str = ""
    webhook_host: str = "http://localhost:8080"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Fragment
    fragment_stel_ssid: str = ""
    fragment_stel_token: str = ""
    fragment_stel_dt: str = ""
    fragment_stel_ton_token: str = ""
    fragment_api_hash: str = ""

    # TON
    ton_mnemonic: str = ""
    ton_wallet_version: str = "v5r1"
    toncenter_api_key: str = ""

    # Misc
    manual_fulfillment: bool = False
    timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"

    @field_validator("required_channel_id", "admin_notify_chat_id", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        # пустая строка в .env / tokens.env = не задано
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.admin_ids_raw.replace(";", ",").split(",") if x.strip().isdigit()]

    @property
    def fragment_cookies(self) -> dict[str, str]:
        return {
            k: v
            for k, v in {
                "stel_ssid": self.fragment_stel_ssid,
                "stel_token": self.fragment_stel_token,
                "stel_dt": self.fragment_stel_dt,
                "stel_ton_token": self.fragment_stel_ton_token,
            }.items()
            if v
        }

    @property
    def fragment_configured(self) -> bool:
        return bool(self.fragment_stel_token and self.fragment_stel_ton_token and self.ton_mnemonic)

    @property
    def click_configured(self) -> bool:
        return bool(self.click_service_id and self.click_merchant_id and self.click_secret_key)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
