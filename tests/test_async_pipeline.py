"""Тесты для модуля async_pipeline."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from async_pipeline import AsyncProcessingPipeline, process_rows_async, run_async_processing
from config import Config
from exceptions import RetryExhaustedError


@pytest.fixture
def mock_config():
    """Мок конфигурации для тестов."""
    config = MagicMock(spec=Config)
    config.use_mocks = True
    config.catalog_timeout_sec = 30
    config.confidence_threshold = 0.7
    config.backoff_base_ms = 100
    config.backoff_max_ms = 2000
    config.backoff_jitter_ms = 100
    return config


@pytest.fixture
def sample_rows():
    """Тестовые данные."""
    return [
        {"partnumber": "ABC123", "brand": "TestBrand"},
        {"partnumber": "XYZ789", "brand": "AnotherBrand"},
        {"partnumber": "", "brand": "EmptyPart"},
    ]


class TestAsyncProcessingPipeline:
    """Тесты для AsyncProcessingPipeline."""

    def test_init(self, mock_config):
        """Тест инициализации пайплайна."""
        pipeline = AsyncProcessingPipeline(mock_config, max_concurrent=5)
        assert pipeline.cfg == mock_config
        assert pipeline.max_concurrent == 5
        assert pipeline.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_async_retry_success(self, mock_config):
        """Тест успешного выполнения с retry."""
        pipeline = AsyncProcessingPipeline(mock_config)
        
        async def mock_func():
            return "success"
        
        result = await pipeline._async_retry(mock_func, attempts=3)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_retry_failure(self, mock_config):
        """Тест исчерпания попыток retry."""
        pipeline = AsyncProcessingPipeline(mock_config)
        
        async def mock_func():
            raise ValueError("Test error")
        
        with pytest.raises(RetryExhaustedError):
            await pipeline._async_retry(mock_func, attempts=2)

    @pytest.mark.asyncio
    async def test_search_catalog_async_mock(self, mock_config):
        """Тест поиска в каталоге с моками."""
        pipeline = AsyncProcessingPipeline(mock_config)
        
        with patch('aiohttp.ClientSession') as mock_session:
            found, found_flag = await pipeline._search_catalog_async(
                mock_session, "ABC123", []
            )
            
            assert found == []
            assert found_flag is False

    @pytest.mark.asyncio
    async def test_classify_llm_async_mock(self, mock_config):
        """Тест классификации LLM с моками."""
        pipeline = AsyncProcessingPipeline(mock_config)
        
        with patch('aiohttp.ClientSession') as mock_session:
            enriched, attrs_norm, confidence = await pipeline._classify_llm_async(
                mock_session, "test text", []
            )
            
            assert enriched == {"gn": "ГН1", "vn": "ВН1"}
            assert attrs_norm == {"category": "test"}
            assert confidence == 0.85

    @pytest.mark.asyncio
    async def test_process_single_row_async_empty_partnumber(self, mock_config):
        """Тест обработки строки с пустым partnumber."""
        pipeline = AsyncProcessingPipeline(mock_config)
        row = {"partnumber": "", "brand": "TestBrand"}
        
        with patch('aiohttp.ClientSession') as mock_session:
            result = await pipeline._process_single_row_async(mock_session, row)
            
            assert result["status"] == "skip"
            assert result["reason"] == "no_partnumber"

    @pytest.mark.asyncio
    async def test_process_single_row_async_valid(self, mock_config):
        """Тест обработки валидной строки."""
        pipeline = AsyncProcessingPipeline(mock_config)
        row = {"partnumber": "ABC123", "brand": "TestBrand"}
        
        with patch('aiohttp.ClientSession') as mock_session:
            result = await pipeline._process_single_row_async(mock_session, row)
            
            assert "status" in result
            assert "action" in result
            assert "reason" in result

    @pytest.mark.asyncio
    async def test_process_batch_async_empty(self, mock_config):
        """Тест обработки пустого пакета."""
        pipeline = AsyncProcessingPipeline(mock_config)
        result = await pipeline.process_batch_async([])
        assert result == []

    @pytest.mark.asyncio
    async def test_process_batch_async_with_data(self, mock_config, sample_rows):
        """Тест обработки пакета с данными."""
        pipeline = AsyncProcessingPipeline(mock_config)
        
        with patch('aiohttp.ClientSession'):
            results = await pipeline.process_batch_async(sample_rows)
            
            assert len(results) == len(sample_rows)
            for result in results:
                assert "status" in result
                assert "action" in result


class TestAsyncFunctions:
    """Тесты для вспомогательных функций."""

    @pytest.mark.asyncio
    async def test_process_rows_async_empty(self, mock_config):
        """Тест обработки пустого списка."""
        result = await process_rows_async([], mock_config)
        assert result == []

    @pytest.mark.asyncio
    async def test_process_rows_async_with_data(self, mock_config, sample_rows):
        """Тест асинхронной обработки данных."""
        with patch('aiohttp.ClientSession'):
            results = await process_rows_async(sample_rows, mock_config)
            assert len(results) == len(sample_rows)

    def test_run_async_processing(self, mock_config, sample_rows):
        """Тест синхронной обертки."""
        with patch('aiohttp.ClientSession'):
            results = run_async_processing(sample_rows, mock_config)
            assert len(results) == len(sample_rows)
