"""Асинхронный пайплайн обработки для ускорения работы с внешними API."""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import List

import aiohttp

from config import Config
from exceptions import RetryExhaustedError
from logger import get_logger


class AsyncProcessingPipeline:
    """Асинхронный класс для обработки строк данных с параллельными запросами к API."""
    
    def __init__(self, cfg: Config, max_concurrent: int = 10):
        self.cfg = cfg
        self.max_concurrent = max_concurrent
        self.log = get_logger("async_pipeline")
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def _async_retry(self, coro_func, *args, attempts: int = 3, errors_list: list | None = None, tag: str = ""):
        """Асинхронная функция retry с exponential backoff."""
        last_exc = None
        for i in range(1, attempts + 1):
            try:
                return await coro_func(*args)
            except Exception as e:
                last_exc = e
                if errors_list is not None:
                    errors_list.append(f"{tag}:{type(e).__name__}:attempt{i}")
                if i < attempts:
                    base = getattr(self.cfg, "backoff_base_ms", 100)
                    max_ms = getattr(self.cfg, "backoff_max_ms", 2000)
                    jitter = getattr(self.cfg, "backoff_jitter_ms", 100)
                    delay_ms = min(max_ms, base * (2 ** (i - 1)))
                    delay_ms += random.randint(0, jitter) if jitter > 0 else 0
                    await asyncio.sleep(delay_ms / 1000.0)
        if last_exc:
            raise RetryExhaustedError(tag, attempts, last_exc) from last_exc
    
    async def _async_http_request(self, session: aiohttp.ClientSession, method: str, url: str, 
                                 headers: dict = None, json_data: dict = None, params: dict = None) -> dict:
        """Выполнение HTTP запроса с обработкой ошибок."""
        timeout = aiohttp.ClientTimeout(total=self.cfg.catalog_timeout_sec)
        
        async with session.request(
            method, url, 
            headers=headers or {}, 
            json=json_data, 
            params=params,
            timeout=timeout
        ) as response:
            if response.status == 200:
                return await response.json()
            elif response.status in (201, 204):
                return {"status": "success"}
            else:
                response.raise_for_status()
    
    async def _search_catalog_async(self, session: aiohttp.ClientSession, partnumber: str, errors: list[str]) -> tuple[list, bool]:
        """Асинхронный поиск в каталоге."""
        if self.cfg.use_mocks:
            # Имитация задержки для мока
            await asyncio.sleep(0.1)
            return [], False
            
        try:
            url = f"{self.cfg.catalog_api_url}/products"
            params = {"partnumber": partnumber}
            headers = {"Authorization": f"Bearer {self.cfg.catalog_api_key}"}
            
            result = await self._async_retry(
                self._async_http_request,
                session, "GET", url, headers, None, params,
                attempts=3, errors_list=errors, tag="catalog_search"
            )
            
            found = result if isinstance(result, list) else []
            return found, bool(found)
            
        except RetryExhaustedError:
            return [], False
    
    async def _classify_llm_async(self, session: aiohttp.ClientSession, text: str, errors: list[str]) -> tuple[dict, dict, float | None]:
        """Асинхронная классификация через LLM."""
        if self.cfg.use_mocks:
            # Имитация задержки для мока
            await asyncio.sleep(0.2)
            return {"gn": "ГН1", "vn": "ВН1"}, {"category": "test"}, 0.85
            
        try:
            # Нормализация
            norm_url = f"{self.cfg.coze_api_url}/normalize"
            norm_payload = {"text": text}
            headers = {"Authorization": f"Bearer {self.cfg.coze_api_key}", "Content-Type": "application/json"}
            
            norm_result = await self._async_retry(
                self._async_http_request,
                session, "POST", norm_url, headers, norm_payload,
                attempts=3, errors_list=errors, tag="llm_normalize"
            )
            
            attrs_norm = norm_result.get("attrs", {})
            
            # Классификация
            classif_url = f"{self.cfg.coze_api_url}/classify"
            classif_payload = {
                "text": text,
                "gn_candidates": ["ГН1", "ГН2", "ГН3"],
                "vn_candidates": ["ВН1", "ВН2", "ВН3"]
            }
            
            classif_result = await self._async_retry(
                self._async_http_request,
                session, "POST", classif_url, headers, classif_payload,
                attempts=3, errors_list=errors, tag="llm_classify"
            )
            
            confidence = classif_result.get("confidence", 0.0)
            
            if confidence < self.cfg.confidence_threshold:
                self.log.info("[llm] low_confidence=%.3f threshold=%.3f text=%s", 
                             confidence, self.cfg.confidence_threshold, text)
                return {}, attrs_norm, confidence
            
            enriched = {"gn": classif_result.get("gn"), "vn": classif_result.get("vn")}
            self.log.info("[llm] ok gn=%s vn=%s conf=%.3f", 
                         enriched["gn"], enriched["vn"], confidence)
            
            return enriched, attrs_norm, confidence
            
        except RetryExhaustedError as e:
            errors.append(f"llm:{type(e).__name__}")
            return {}, {}, None
    
    async def _process_single_row_async(self, session: aiohttp.ClientSession, row: dict) -> dict:
        """Асинхронная обработка одной строки данных."""
        async with self.semaphore:  # Ограничение параллельных запросов
            part = str(row.get("partnumber", "")).strip()
            brand = str(row.get("brand", "")).strip()
            
            if not part:
                row.update({"status": "skip", "reason": "no_partnumber"})
                return row
            
            decision = {"action": "skip", "reason": "no_partnumber"}
            enriched = {}
            found_flag = False
            confidence_val = None
            attrs_norm: dict = {}
            errors: list[str] = []
            
            # 1. Поиск в каталоге
            found, found_flag = await self._search_catalog_async(session, part, errors)
            
            if found:
                # Товар найден в каталоге
                decision = {"action": "skip", "reason": "already_present"}
            else:
                # 2. Классификация LLM
                text = f"{part} {brand}".strip()
                enriched, attrs_norm, confidence_val = await self._classify_llm_async(session, text, errors)
                
                if confidence_val is not None and confidence_val < self.cfg.confidence_threshold:
                    decision = {"action": "skip", "reason": "low_confidence"}
                else:
                    decision = {"action": "create", "reason": "not_found"}
            
            # Формирование результата
            row.update({
                "status": decision["action"],
                "action": decision["action"],
                "reason": decision["reason"],
                "found_in_catalog": found_flag,
                "confidence": confidence_val if confidence_val is not None else "",
                "attrs_norm": json.dumps(attrs_norm, ensure_ascii=False) if attrs_norm else "",
                "errors": ";".join(errors) if errors else "",
                **enriched,
            })
            
            return row
    
    async def process_batch_async(self, rows: List[dict]) -> List[dict]:
        """Асинхронная обработка пакета строк."""
        if not rows:
            return []
        
        self.log.info("[async_pipeline] Starting async processing of %d rows with max_concurrent=%d", 
                     len(rows), self.max_concurrent)
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Создаем задачи для всех строк
            tasks = [
                self._process_single_row_async(session, row.copy()) 
                for row in rows
            ]
            
            # Выполняем все задачи параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты и исключения
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.log.error("[async_pipeline] Error processing row %d: %s", i, result)
                    error_row = rows[i].copy()
                    error_row.update({
                        "status": "error", 
                        "reason": f"async_error: {type(result).__name__}",
                        "errors": f"async:{type(result).__name__}"
                    })
                    processed_results.append(error_row)
                else:
                    processed_results.append(result)
        
        elapsed = time.time() - start_time
        self.log.info("[async_pipeline] Completed processing %d rows in %.2f seconds (%.4f sec/row)", 
                     len(rows), elapsed, elapsed / len(rows))
        
        return processed_results


async def process_rows_async(data: list, cfg: Config, max_concurrent: int = 10) -> list:
    """Асинхронная обработка строк данных."""
    if not data:
        return []
    
    pipeline = AsyncProcessingPipeline(cfg, max_concurrent)
    return await pipeline.process_batch_async(data)


def run_async_processing(data: list, cfg: Config, max_concurrent: int = 10) -> list:
    """Синхронная обертка для асинхронной обработки."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(process_rows_async(data, cfg, max_concurrent))
    finally:
        if loop.is_running():
            loop.close()
