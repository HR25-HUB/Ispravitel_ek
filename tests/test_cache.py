"""Тесты для модуля cache."""
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cache import LRUCache, PersistentCache, LLMCache, get_llm_cache


class TestLRUCache:
    """Тесты для LRU кэша."""

    def test_init(self):
        """Тест инициализации."""
        cache = LRUCache(max_size=5)
        assert cache.max_size == 5
        assert cache.size() == 0

    def test_put_and_get(self):
        """Тест добавления и получения значений."""
        cache = LRUCache(max_size=3)
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        """Тест вытеснения по LRU."""
        cache = LRUCache(max_size=2)
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")  # Должно вытеснить key1
        
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_access_updates_lru(self):
        """Тест обновления времени доступа."""
        cache = LRUCache(max_size=2)
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        
        # Обращаемся к key1, чтобы обновить время доступа
        cache.get("key1")
        
        # Добавляем key3, должно вытеснить key2
        cache.put("key3", "value3")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"

    def test_clear(self):
        """Тест очистки кэша."""
        cache = LRUCache()
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        
        cache.clear()
        
        assert cache.size() == 0
        assert cache.get("key1") is None


class TestPersistentCache:
    """Тесты для персистентного кэша."""

    def test_init(self):
        """Тест инициализации."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir, max_age_hours=1)
            assert cache.cache_dir == Path(temp_dir)
            assert cache.max_age_seconds == 3600

    def test_put_and_get(self):
        """Тест сохранения и загрузки."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir)
            
            cache.put("test_key", {"data": "test_value"})
            result = cache.get("test_key")
            
            assert result == {"data": "test_value"}

    def test_get_nonexistent(self):
        """Тест получения несуществующего ключа."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir)
            result = cache.get("nonexistent_key")
            assert result is None

    def test_expired_cache(self):
        """Тест истекшего кэша."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir, max_age_hours=0)  # Мгновенное истечение
            
            cache.put("test_key", "test_value")
            time.sleep(0.1)  # Небольшая задержка
            
            result = cache.get("test_key")
            assert result is None

    def test_clear_expired(self):
        """Тест очистки истекших записей."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir, max_age_hours=0)
            
            cache.put("key1", "value1")
            cache.put("key2", "value2")
            time.sleep(0.1)
            
            cleared = cache.clear_expired()
            assert cleared == 2

    def test_clear_all(self):
        """Тест полной очистки кэша."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = PersistentCache(temp_dir)
            
            cache.put("key1", "value1")
            cache.put("key2", "value2")
            
            cleared = cache.clear_all()
            assert cleared == 2
            
            assert cache.get("key1") is None
            assert cache.get("key2") is None


class TestLLMCache:
    """Тесты для LLM кэша."""

    def test_init(self):
        """Тест инициализации."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(memory_cache_size=100, cache_dir=temp_dir)
            assert cache.memory_cache.max_size == 100

    def test_normalize_key(self):
        """Тест нормализации ключей."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            key1 = cache._normalize_key("  Test   Text  ", "classify")
            key2 = cache._normalize_key("test text", "classify")
            
            assert key1 == key2 == "classify:test text"

    def test_classification_cache(self):
        """Тест кэширования классификации."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            text = "Test component"
            result = {"gn": "ГН1", "vn": "ВН1", "confidence": 0.9}
            
            # Сохраняем
            cache.put_classification(text, result)
            
            # Загружаем
            cached_result = cache.get_classification(text)
            assert cached_result == result

    def test_normalization_cache(self):
        """Тест кэширования нормализации."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            text = "Test component"
            result = {"normalized": "test component", "attrs": {"type": "resistor"}}
            
            # Сохраняем
            cache.put_normalization(text, result)
            
            # Загружаем
            cached_result = cache.get_normalization(text)
            assert cached_result == result

    def test_cache_miss(self):
        """Тест промаха кэша."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            result = cache.get_classification("nonexistent text")
            assert result is None

    def test_memory_to_disk_promotion(self):
        """Тест продвижения из памяти на диск."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(memory_cache_size=1, cache_dir=temp_dir)
            
            # Сохраняем в память и на диск
            cache.put_classification("text1", {"result": "1"})
            
            # Очищаем память
            cache.memory_cache.clear()
            
            # Должно загрузиться с диска и попасть в память
            result = cache.get_classification("text1")
            assert result == {"result": "1"}
            
            # Проверяем, что теперь в памяти
            memory_result = cache.memory_cache.get("classify:text1")
            assert memory_result == {"result": "1"}

    def test_get_stats(self):
        """Тест получения статистики."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            cache.put_classification("text1", {"result": "1"})
            
            stats = cache.get_stats()
            
            assert "memory_cache_size" in stats
            assert "memory_cache_max_size" in stats
            assert "disk_cache_dir" in stats
            assert "disk_cache_files" in stats

    def test_clear_all(self):
        """Тест полной очистки."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LLMCache(cache_dir=temp_dir)
            
            cache.put_classification("text1", {"result": "1"})
            cache.put_normalization("text2", {"result": "2"})
            
            cache.clear_all()
            
            assert cache.get_classification("text1") is None
            assert cache.get_normalization("text2") is None


class TestGlobalCache:
    """Тесты для глобального кэша."""

    def test_get_llm_cache_singleton(self):
        """Тест синглтона глобального кэша."""
        with patch('cache._llm_cache', None):
            cache1 = get_llm_cache()
            cache2 = get_llm_cache()
            
            assert cache1 is cache2
