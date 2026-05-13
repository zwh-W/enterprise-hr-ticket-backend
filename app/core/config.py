"""Application configuration.

本文件负责把配置从三个来源合并成一个 Settings 对象：
1. 运行时传入的初始化参数，优先级最高，一般只在测试中使用。
2. 环境变量和 .env 文件，适合 Docker / 本机开发 / 生产部署。
3. config.yaml，作为项目级默认配置，便于集中阅读默认值。

优先级规则：init 参数 > 环境变量 > .env > config.yaml > 类默认值。
这意味着敏感信息仍然应该放在 .env 或环境变量中，而不是写进 config.yaml。
"""

from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """pydantic-settings 自定义配置源：从 config.yaml 读取默认配置。

    这个类只提供非敏感默认值。真正部署时，.env 或环境变量会覆盖它。
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self.yaml_data = self._load_yaml_config()

    def _load_yaml_config(self) -> dict[str, Any]:
        """读取 YAML 配置文件。

        CONFIG_YAML_PATH 支持通过环境变量指定配置文件位置。
        默认读取项目根目录下的 config.yaml。
        """
        config_path = Path(os.getenv("CONFIG_YAML_PATH", BASE_DIR / "config.yaml"))
        if not config_path.exists():
            return {}

        with config_path.open("r", encoding="utf-8") as file:
            raw_data = yaml.safe_load(file) or {}

        # 只接受顶层 key-value 配置，避免嵌套配置导致字段名不直观。
        if not isinstance(raw_data, dict):
            return {}
        return raw_data

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """按字段名从 YAML 字典中取值。

        第三个返回值 value_is_complex 表示是否需要额外解析复杂类型。
        当前配置都是基础类型，所以返回 False。
        """
        value = self.yaml_data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        """返回完整 YAML 配置字典。"""
        return self.yaml_data


class Settings(BaseSettings):
    """项目运行配置。

    字段名使用 snake_case；环境变量通常使用大写形式，例如 DATABASE_URL。
    """

    app_name: str = "enterprise-hr-ticket-backend"
    environment: str = "local"
    debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/enterprise_hr_ticket"
    test_database_url: str = "sqlite+pysqlite:///:memory:"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    internal_api_key: str = "change-me-internal-api-key"

    redis_url: str = "redis://localhost:6379/0"

    # 第二阶段新增：幂等记录保留时间。
    # 后续可以用定时任务清理过期 idempotency_keys。
    idempotency_key_ttl_hours: int = 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """声明配置源优先级。

        注意：YAML 的优先级低于环境变量和 .env，因此不会覆盖敏感配置。
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    """返回全局 Settings 单例。

    lru_cache 用来避免每次请求都重新读取 .env / config.yaml。
    测试中如果要修改环境变量，需要先 get_settings.cache_clear()。
    """
    return Settings()
