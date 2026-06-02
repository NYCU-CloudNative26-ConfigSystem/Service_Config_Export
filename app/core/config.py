from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "Config Export Service"
    app_version: str = "1.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 18005
    app_reload: bool = False
    secret_key: str = "test-secret-key-for-ci"
    algorithm: str = "HS256"
    config_service_url: str = "http://localhost:18001"
    ssot_service_url: str = "http://localhost:3000"


settings = Settings()
