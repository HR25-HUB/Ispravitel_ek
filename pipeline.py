"""Модуль пайплайна обработки строк данных."""
from __future__ import annotations

import json
import random
import time
from config import Config
from exceptions import RetryExhaustedError
from logger import get_logger


class ProcessingPipeline:
    """Класс для обработки строк данных с разделением логики на этапы."""
    
    def __init__(self, cfg: Config, catalog_client, lcsc_client=None, llm_client=None):
        self.cfg = cfg
        self.catalog = catalog_client
        self.lcsc = lcsc_client
        self.llm = llm_client
        self.log = get_logger("pipeline")
    
    def _retry(self, callable_, *args, attempts: int = 3, errors_list: list | None = None, tag: str = ""):
        """Универсальная функция retry с exponential backoff."""
        last_exc = None
        for i in range(1, attempts + 1):
            try:
                return callable_(*args)
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
                    time.sleep(delay_ms / 1000.0)
        if last_exc:
            raise RetryExhaustedError(tag, attempts, last_exc) from last_exc
    
    def _search_in_catalog(self, partnumber: str, errors: list[str]) -> tuple[list, bool]:
        """Поиск товара в каталоге."""
        try:
            found = self._retry(
                self.catalog.search_product, 
                partnumber, 
                attempts=3, 
                errors_list=errors, 
                tag="catalog_search"
            )
            return found, bool(found)
        except RetryExhaustedError:
            return [], False
    
    def _update_catalog_product(self, product_id: str | int, patch: dict, errors: list[str]) -> dict:
        """Обновление товара в каталоге."""
        if not hasattr(self.catalog, "update_product"):
            return {"action": "conflict", "reason": "update_not_supported"}
        
        try:
            self._retry(
                self.catalog.update_product, 
                product_id, 
                patch, 
                attempts=3, 
                errors_list=errors, 
                tag="catalog_update"
            )
            self.log.info("[catalog] update id=%s patch=%s", product_id, list(patch.keys()))
            return {"action": "update", "reason": "fields_mismatch"}
        except RetryExhaustedError:
            return {"action": "conflict", "reason": "update_failed"}
    
    def _search_in_lcsc(self, partnumber: str, errors: list[str]) -> list:
        """Поиск товара в LCSC."""
        if self.lcsc is None:
            return []
        
        try:
            candidates = self._retry(
                self.lcsc.search, 
                partnumber, 
                attempts=3, 
                errors_list=errors, 
                tag="lcsc_search"
            )
            self.log.info("[lcsc] candidates=%s for part=%s", len(candidates), partnumber)
            return candidates
        except RetryExhaustedError:
            return []
    
    def _classify_with_llm(self, text: str, errors: list[str]) -> tuple[dict, dict, float | None]:
        """Классификация и нормализация через LLM."""
        if self.llm is None:
            return {}, {}, None
        
        try:
            norm = self.llm.normalize(text)
            attrs_norm = norm.get("attrs") or {}
            
            classif = self.llm.classify(["ГН1", "ГН2", "ГН3"], ["ВН1", "ВН2", "ВН3"], text)
            confidence = classif.get("confidence")
            
            if (confidence or 0.0) < self.cfg.confidence_threshold:
                self.log.info(
                    "[llm] low_confidence=%.3f threshold=%.3f part=%s", 
                    confidence or 0.0, self.cfg.confidence_threshold, text
                )
                return {}, attrs_norm, confidence
            
            enriched = {"gn": classif.get("gn"), "vn": classif.get("vn")}
            self.log.info(
                "[llm] ok gn=%s vn=%s conf=%.3f", 
                classif.get("gn"), classif.get("vn"), confidence or 0.0
            )
            return enriched, attrs_norm, confidence
            
        except RetryExhaustedError as e:
            errors.append(f"llm:{type(e).__name__}")
            return {}, {}, None
    
    def _create_catalog_product(self, partnumber: str, brand: str, norm: dict, 
                               attrs_norm: dict, enriched: dict, row: dict, errors: list[str]) -> dict:
        """Создание товара в каталоге."""
        if not hasattr(self.catalog, "create_product"):
            return {"action": "skip", "reason": "not_found"}
        
        try:
            payload = {
                "partnumber": partnumber,
                "name": norm.get("local_name") or partnumber,
                "brand": brand,
                "attrs": attrs_norm or {},
            }
            
            # Добавляем дополнительные поля если есть
            ext_in = str(row.get("external_id", "")).strip()
            if ext_in:
                payload["external_id"] = ext_in
            if enriched.get("gn"):
                payload["gn"] = enriched.get("gn")
            if enriched.get("vn"):
                payload["vn"] = enriched.get("vn")
            
            self._retry(
                self.catalog.create_product, 
                payload, 
                attempts=3, 
                errors_list=errors, 
                tag="catalog_create"
            )
            self.log.info("[catalog] create part=%s brand=%s", partnumber, payload.get("brand"))
            return {"action": "create", "reason": "not_found"}
            
        except RetryExhaustedError:
            return {"action": "conflict", "reason": "create_failed"}
    
    def process_single_row(self, row: dict) -> dict:
        """Обработка одной строки данных."""
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
        found, found_flag = self._search_in_catalog(part, errors)
        
        if found:
            # Обновление существующего товара
            best = found[0]
            patch = self._build_update_patch(row, best, brand)
            
            if patch:
                decision = self._update_catalog_product(best.get("id"), patch, errors)
            else:
                decision = {"action": "skip", "reason": "already_present"}
        else:
            # 2. Поиск в LCSC
            candidates = self._search_in_lcsc(part, errors)
            decision = {"action": "skip", "reason": "not_found"}
            
            # 3. Классификация LLM
            text = f"{part} {brand}".strip()
            enriched, attrs_norm, confidence_val = self._classify_with_llm(text, errors)
            
            if confidence_val is not None and confidence_val < self.cfg.confidence_threshold:
                decision = {"action": "skip", "reason": "low_confidence"}
            elif decision["reason"] == "not_found":
                # 4. Создание в каталоге
                norm = {"local_name": part}  # Упрощенная нормализация
                decision = self._create_catalog_product(
                    part, brand or (candidates[0]["brand"] if candidates else ""),
                    norm, attrs_norm, enriched, row, errors
                )
        
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
    
    def _build_update_patch(self, row: dict, existing: dict, brand: str) -> dict:
        """Построение патча для обновления товара."""
        patch = {}
        
        # Обновление brand при расхождении
        if brand and existing.get("brand") and existing.get("brand") != brand:
            patch["brand"] = brand
        
        # Обновление external_id
        ext_in = str(row.get("external_id", "")).strip()
        if ext_in and (existing.get("external_id") or "") != ext_in:
            patch["external_id"] = ext_in
        
        # Обновление gn/vn
        gn_in = str(row.get("gn", "")).strip()
        vn_in = str(row.get("vn", "")).strip()
        if gn_in and (existing.get("gn") or "") != gn_in:
            patch["gn"] = gn_in
        if vn_in and (existing.get("vn") or "") != vn_in:
            patch["vn"] = vn_in
        
        return patch
