"""Система кэширования для LLM результатов и других дорогих операций."""
from __future__ import annotations

import hashlib
import pickle
import time
from pathlib import Path
from typing import Any, Dict, Optional

from logger import get_logger


class LRUCache:
    """Простая реализация LRU кэша."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, Any] = {}
        self.access_times: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша."""
        if key in self.cache:
            self.access_times[key] = time.time()
            return self.cache[key]
        return None
    
    def put(self, key: str, value: Any) -> None:
        """Добавить значение в кэш."""
        current_time = time.time()
        
        # Если кэш переполнен, удаляем самый старый элемент
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        
        self.cache[key] = value
        self.access_times[key] = current_time
    
    def clear(self) -> None:
        """Очистить кэш."""
        self.cache.clear()
        self.access_times.clear()
    
    def size(self) -> int:
        """Размер кэша."""
        return len(self.cache)


class PersistentCache:
    """Персистентный кэш с сохранением на диск."""
    
    def __init__(self, cache_dir: str = "cache", max_age_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.max_age_seconds = max_age_hours * 3600
        self.log = get_logger("cache")
        
        # Создаем директорию кэша
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_path(self, key: str) -> Path:
        """Получить путь к файлу кэша для ключа."""
        # Хэшируем ключ для безопасного имени файла
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"
    
    def _is_expired(self, cache_path: Path) -> bool:
        """Проверить, истек ли срок действия кэша."""
        if not cache_path.exists():
            return True
        
        file_age = time.time() - cache_path.stat().st_mtime
        return file_age > self.max_age_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из персистентного кэша."""
        cache_path = self._get_cache_path(key)
        
        if self._is_expired(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
                self.log.debug("[cache] Hit for key: %s", key[:50])
                return data
        except Exception as e:
            self.log.warning("[cache] Failed to load cache for key %s: %s", key[:50], e)
            return None
    
    def put(self, key: str, value: Any) -> None:
        """Сохранить значение в персистентный кэш."""
        cache_path = self._get_cache_path(key)
        
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(value, f)
                self.log.debug("[cache] Stored key: %s", key[:50])
        except Exception as e:
            self.log.warning("[cache] Failed to store cache for key %s: %s", key[:50], e)
    
    def clear_expired(self) -> int:
        """Очистить истекшие записи кэша."""
        cleared = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            if self._is_expired(cache_file):
                try:
                    cache_file.unlink()
                    cleared += 1
                except Exception as e:
                    self.log.warning("[cache] Failed to delete expired cache %s: %s", cache_file, e)
        
        if cleared > 0:
            self.log.info("[cache] Cleared %d expired cache entries", cleared)
        
        return cleared
    
    def clear_all(self) -> int:
        """Очистить весь кэш."""
        cleared = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                cache_file.unlink()
                cleared += 1
            except Exception as e:
                self.log.warning("[cache] Failed to delete cache %s: %s", cache_file, e)
        
        self.log.info("[cache] Cleared all %d cache entries", cleared)
        return cleared


class LLMCache:
    """Специализированный кэш для LLM результатов."""
    
    def __init__(self, memory_cache_size: int = 500, cache_dir: str = "cache/llm", max_age_hours: int = 168):
        self.memory_cache = LRUCache(memory_cache_size)
        self.disk_cache = PersistentCache(cache_dir, max_age_hours)  # 7 дней по умолчанию
        self.log = get_logger("llm_cache")
    
    def _normalize_key(self, text: str, operation: str = "classify") -> str:
        """Нормализовать ключ для кэширования."""
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized_text = " ".join(text.lower().split())
        return f"{operation}:{normalized_text}"
    
    def get_classification(self, text: str) -> Optional[Dict[str, Any]]:
        """Получить результат классификации из кэша."""
        key = self._normalize_key(text, "classify")
        
        # Сначала проверяем память
        result = self.memory_cache.get(key)
        if result is not None:
            self.log.debug("[llm_cache] Memory hit for text: %s", text[:50])
            return result
        
        # Затем проверяем диск
        result = self.disk_cache.get(key)
        if result is not None:
            # Загружаем в память для быстрого доступа
            self.memory_cache.put(key, result)
            self.log.debug("[llm_cache] Disk hit for text: %s", text[:50])
            return result
        
        self.log.debug("[llm_cache] Miss for text: %s", text[:50])
        return None
    
    def put_classification(self, text: str, result: Dict[str, Any]) -> None:
        """Сохранить результат классификации в кэш."""
        key = self._normalize_key(text, "classify")
        
        # Сохраняем в оба кэша
        self.memory_cache.put(key, result)
        self.disk_cache.put(key, result)
        
        self.log.debug("[llm_cache] Stored classification for text: %s", text[:50])
    
    def get_normalization(self, text: str) -> Optional[Dict[str, Any]]:
        """Получить результат нормализации из кэша."""
        key = self._normalize_key(text, "normalize")
        
        result = self.memory_cache.get(key)
        if result is not None:
            return result
        
        result = self.disk_cache.get(key)
        if result is not None:
            self.memory_cache.put(key, result)
            return result
        
        return None
    
    def put_normalization(self, text: str, result: Dict[str, Any]) -> None:
        """Сохранить результат нормализации в кэш."""
        key = self._normalize_key(text, "normalize")
        
        self.memory_cache.put(key, result)
        self.disk_cache.put(key, result)
        
        self.log.debug("[llm_cache] Stored normalization for text: %s", text[:50])
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику кэша."""
        return {
            "memory_cache_size": self.memory_cache.size(),
            "memory_cache_max_size": self.memory_cache.max_size,
            "disk_cache_dir": str(self.disk_cache.cache_dir),
            "disk_cache_files": len(list(self.disk_cache.cache_dir.glob("*.cache"))),
        }
    
    def clear_expired(self) -> int:
        """Очистить истекшие записи."""
        return self.disk_cache.clear_expired()
    
    def clear_all(self) -> None:
        """Очистить весь кэш."""
        self.memory_cache.clear()
        self.disk_cache.clear_all()
        self.log.info("[llm_cache] Cleared all caches")


# Глобальный экземпляр кэша
_llm_cache: Optional[LLMCache] = None


def get_llm_cache() -> LLMCache:
    """Получить глобальный экземпляр LLM кэша."""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache()
    return _llm_cache
