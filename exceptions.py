"""Пользовательские исключения для проекта bot_ispravitel."""
from __future__ import annotations


class BotIspravitelError(Exception):
    """Базовое исключение для всех ошибок бота."""
    pass


class ConfigurationError(BotIspravitelError):
    """Ошибка конфигурации."""
    pass


class ValidationError(BotIspravitelError):
    """Ошибка валидации данных."""
    pass


class ExternalServiceError(BotIspravitelError):
    """Ошибка внешнего сервиса."""
    
    def __init__(self, service_name: str, message: str, original_error: Exception | None = None):
        self.service_name = service_name
        self.original_error = original_error
        super().__init__(f"{service_name}: {message}")


class CatalogAPIError(ExternalServiceError):
    """Ошибка Catalog API."""
    
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__("CatalogAPI", message, original_error)


class LCSCError(ExternalServiceError):
    """Ошибка LCSC API."""
    
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__("LCSC", message, original_error)


class LLMError(ExternalServiceError):
    """Ошибка LLM сервиса."""
    
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__("LLM", message, original_error)


class RetryExhaustedError(BotIspravitelError):
    """Исчерпаны попытки повтора операции."""
    
    def __init__(self, operation: str, attempts: int, last_error: Exception):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Retry exhausted for {operation} after {attempts} attempts: {last_error}")
