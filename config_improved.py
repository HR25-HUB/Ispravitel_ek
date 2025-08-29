"""Улучшенная система конфигурации с расширенной валидацией."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv

from exceptions import ConfigurationError

VALID_MOCK_PROFILES = {"happy", "conflict", "missing", "errorrate10", "timeout"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class DatabaseConfig:
    """Конфигурация базы данных (для будущего расширения)."""
    url: Optional[str] = None
    pool_size: int = 5
    timeout_sec: float = 30.0


@dataclass(frozen=True)
class RetryConfig:
    """Конфигурация повторных попыток."""
    attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 2000
    jitter_ms: int = 100
    
    def __post_init__(self):
        if self.attempts < 1:
            raise ConfigurationError("Retry attempts must be >= 1")
        if self.base_delay_ms < 0:
            raise ConfigurationError("Base delay must be >= 0")
        if self.max_delay_ms < self.base_delay_ms:
            raise ConfigurationError("Max delay must be >= base delay")


@dataclass(frozen=True)
class ServiceConfig:
    """Базовая конфигурация сервиса."""
    api_url: Optional[str]
    api_key: Optional[str]
    timeout_sec: float
    retry: RetryConfig


@dataclass(frozen=True)
class Config:
    """Расширенная конфигурация приложения."""
    # Сервисы
    catalog: ServiceConfig
    lcsc: ServiceConfig
    llm: ServiceConfig
    
    # Мокирование
    use_mocks: bool
    mock_profile: str
    seed: int
    
    # Обработка
    confidence_threshold: float
    batch_size: int
    max_workers: int
    
    # Планировщик
    agent_schedule: str
    input_path: Optional[str]
    output_dir: str
    
    # Система
    log_level: str
    streamlit_port: int
    
    # База данных (для будущего)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    # Дополнительные настройки
    features: Set[str] = field(default_factory=set)
    limits: Dict[str, int] = field(default_factory=dict)
    
    @property
    def is_catalog_required(self) -> bool:
        return not self.use_mocks
    
    @property
    def is_parallel_processing_enabled(self) -> bool:
        return self.max_workers > 1 and "parallel_processing" in self.features


class ConfigValidator:
    """Валидатор конфигурации."""
    
    @staticmethod
    def validate_schedule(schedule: str) -> None:
        """Валидация расписания."""
        if not re.fullmatch(r"\d{2}:\d{2}", schedule):
            raise ConfigurationError("AGENT_SCHEDULE must be in HH:MM format")
        
        try:
            hh, mm = schedule.split(":")
            h, m = int(hh), int(mm)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ConfigurationError("Invalid hour/minute values in AGENT_SCHEDULE")
        except ValueError as e:
            raise ConfigurationError("Invalid AGENT_SCHEDULE format") from e
    
    @staticmethod
    def validate_confidence_threshold(threshold: float) -> None:
        """Валидация порога уверенности."""
        if not (0.0 <= threshold <= 1.0):
            raise ConfigurationError("CONFIDENCE_THRESHOLD must be between 0.0 and 1.0")
    
    @staticmethod
    def validate_mock_profile(profile: str) -> None:
        """Валидация профиля мока."""
        if profile not in VALID_MOCK_PROFILES:
            raise ConfigurationError(
                f"MOCK_PROFILE must be one of {sorted(VALID_MOCK_PROFILES)}, got: {profile}"
            )
    
    @staticmethod
    def validate_log_level(level: str) -> None:
        """Валидация уровня логирования."""
        if level.upper() not in VALID_LOG_LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")
    
    @staticmethod
    def validate_required_for_production(config: Config) -> None:
        """Валидация обязательных настроек для продакшена."""
        if config.use_mocks:
            return
        
        missing = []
        if not config.catalog.api_url:
            missing.append("CATALOG_API_URL")
        if not config.catalog.api_key:
            missing.append("CATALOG_API_KEY")
        
        if missing:
            raise ConfigurationError(
                f"Missing required settings for production: {', '.join(missing)}"
            )
    
    @staticmethod
    def validate_paths(config: Config) -> None:
        """Валидация путей."""
        if config.input_path and not Path(config.input_path).exists():
            raise ConfigurationError(f"Input file not found: {config.input_path}")
        
        try:
            Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ConfigurationError(f"Cannot create output directory {config.output_dir}: {e}") from e


def _get_env_bool(name: str, default: bool) -> bool:
    """Получить boolean из переменной окружения."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_env_int(name: str, default: int) -> int:
    """Получить int из переменной окружения."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigurationError(f"Environment variable {name} must be integer, got: {raw}") from e


def _get_env_float(name: str, default: float) -> float:
    """Получить float из переменной окружения."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ConfigurationError(f"Environment variable {name} must be float, got: {raw}") from e


def _get_env_set(name: str, default: Set[str] | None = None) -> Set[str]:
    """Получить set из переменной окружения (через запятую)."""
    raw = os.getenv(name)
    if not raw:
        return default or set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _create_retry_config(prefix: str) -> RetryConfig:
    """Создать конфигурацию повторов для сервиса."""
    return RetryConfig(
        attempts=_get_env_int(f"{prefix}_RETRIES", 3),
        base_delay_ms=_get_env_int(f"{prefix}_BACKOFF_BASE_MS", 100),
        max_delay_ms=_get_env_int(f"{prefix}_BACKOFF_MAX_MS", 2000),
        jitter_ms=_get_env_int(f"{prefix}_BACKOFF_JITTER_MS", 100),
    )


def _create_service_config(prefix: str, default_timeout: float = 10.0) -> ServiceConfig:
    """Создать конфигурацию сервиса."""
    return ServiceConfig(
        api_url=os.getenv(f"{prefix}_API_URL"),
        api_key=os.getenv(f"{prefix}_API_KEY"),
        timeout_sec=_get_env_float(f"{prefix}_TIMEOUT_SEC", default_timeout),
        retry=_create_retry_config(prefix),
    )


def load_config_improved(override_dotenv_path: Optional[str] = None) -> Config:
    """Загрузка улучшенной конфигурации."""
    load_dotenv(dotenv_path=override_dotenv_path, override=False)
    
    # Основные настройки
    use_mocks = _get_env_bool("USE_MOCKS", True)
    mock_profile = os.getenv("MOCK_PROFILE", "happy").strip().lower()
    
    # Создание конфигурации
    config = Config(
        # Сервисы
        catalog=_create_service_config("CATALOG"),
        lcsc=_create_service_config("LCSC"),
        llm=_create_service_config("LLM", 15.0),
        
        # Мокирование
        use_mocks=use_mocks,
        mock_profile=mock_profile,
        seed=_get_env_int("SEED", 42),
        
        # Обработка
        confidence_threshold=_get_env_float("CONFIDENCE_THRESHOLD", 0.7),
        batch_size=_get_env_int("BATCH_SIZE", 100),
        max_workers=_get_env_int("MAX_WORKERS", 1),
        
        # Планировщик
        agent_schedule=os.getenv("AGENT_SCHEDULE", "03:00"),
        input_path=os.getenv("INPUT_PATH"),
        output_dir=os.getenv("OUTPUT_DIR", "reports"),
        
        # Система
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        streamlit_port=_get_env_int("STREAMLIT_PORT", 8501),
        
        # База данных
        database=DatabaseConfig(
            url=os.getenv("DATABASE_URL"),
            pool_size=_get_env_int("DB_POOL_SIZE", 5),
            timeout_sec=_get_env_float("DB_TIMEOUT_SEC", 30.0),
        ),
        
        # Дополнительные настройки
        features=_get_env_set("FEATURES"),
        limits={
            "max_file_size_mb": _get_env_int("MAX_FILE_SIZE_MB", 100),
            "max_rows_per_batch": _get_env_int("MAX_ROWS_PER_BATCH", 10000),
        },
    )
    
    # Валидация
    validator = ConfigValidator()
    validator.validate_schedule(config.agent_schedule)
    validator.validate_confidence_threshold(config.confidence_threshold)
    validator.validate_mock_profile(config.mock_profile)
    validator.validate_log_level(config.log_level)
    validator.validate_required_for_production(config)
    validator.validate_paths(config)
    
    return config
