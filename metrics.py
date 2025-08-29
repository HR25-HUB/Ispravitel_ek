"""Система метрик и мониторинга для bot_ispravitel."""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List

from logger import get_logger


@dataclass
class ProcessingMetrics:
    """Метрики обработки данных."""
    total_rows: int = 0
    processed_rows: int = 0
    failed_rows: int = 0
    
    # Действия
    created: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: int = 0
    
    # Времена выполнения
    processing_time: float = 0.0
    avg_row_time: float = 0.0
    
    # Ошибки по сервисам
    catalog_errors: int = 0
    lcsc_errors: int = 0
    llm_errors: int = 0
    
    # Детальная статистика
    reasons: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    confidence_stats: List[float] = field(default_factory=list)
    
    def add_result(self, row: dict):
        """Добавить результат обработки строки."""
        self.processed_rows += 1
        
        action = row.get("action", "unknown")
        if action == "create":
            self.created += 1
        elif action == "update":
            self.updated += 1
        elif action == "skip":
            self.skipped += 1
        elif action in ("conflict", "error"):
            self.conflicts += 1
        
        reason = row.get("reason", "unknown")
        self.reasons[reason] += 1
        
        # Статистика уверенности
        confidence = row.get("confidence")
        if confidence and isinstance(confidence, (int, float)):
            self.confidence_stats.append(float(confidence))
        
        # Подсчет ошибок по сервисам
        errors = row.get("errors", "")
        if errors:
            if "catalog" in errors:
                self.catalog_errors += 1
            if "lcsc" in errors:
                self.lcsc_errors += 1
            if "llm" in errors:
                self.llm_errors += 1
    
    def finalize(self, processing_time: float):
        """Финализация метрик."""
        self.processing_time = processing_time
        if self.processed_rows > 0:
            self.avg_row_time = processing_time / self.processed_rows
    
    def get_summary(self) -> dict:
        """Получить сводку метрик."""
        success_rate = (self.processed_rows - self.failed_rows) / max(self.total_rows, 1) * 100
        
        confidence_avg = sum(self.confidence_stats) / len(self.confidence_stats) if self.confidence_stats else 0
        
        return {
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "success_rate": round(success_rate, 2),
            "processing_time": round(self.processing_time, 2),
            "avg_row_time": round(self.avg_row_time, 4),
            "actions": {
                "created": self.created,
                "updated": self.updated,
                "skipped": self.skipped,
                "conflicts": self.conflicts,
            },
            "errors": {
                "catalog": self.catalog_errors,
                "lcsc": self.lcsc_errors,
                "llm": self.llm_errors,
            },
            "confidence": {
                "average": round(confidence_avg, 3),
                "count": len(self.confidence_stats),
            },
            "top_reasons": dict(sorted(self.reasons.items(), key=lambda x: x[1], reverse=True)[:5])
        }


class MetricsCollector:
    """Сборщик метрик для мониторинга."""
    
    def __init__(self):
        self.log = get_logger("metrics")
        self.metrics = ProcessingMetrics()
        self._start_time = None
    
    @contextmanager
    def processing_timer(self):
        """Контекстный менеджер для измерения времени обработки."""
        self._start_time = time.time()
        try:
            yield
        finally:
            if self._start_time:
                elapsed = time.time() - self._start_time
                self.metrics.finalize(elapsed)
    
    def set_total_rows(self, count: int):
        """Установить общее количество строк."""
        self.metrics.total_rows = count
    
    def add_result(self, row: dict):
        """Добавить результат обработки."""
        self.metrics.add_result(row)
    
    def log_summary(self):
        """Записать сводку в лог."""
        summary = self.metrics.get_summary()
        
        self.log.info("[metrics] Processing completed:")
        self.log.info("[metrics] Total: %d, Processed: %d, Success rate: %.1f%%", 
                     summary["total_rows"], summary["processed_rows"], summary["success_rate"])
        self.log.info("[metrics] Time: %.2fs (avg %.4fs per row)", 
                     summary["processing_time"], summary["avg_row_time"])
        self.log.info("[metrics] Actions - Created: %d, Updated: %d, Skipped: %d, Conflicts: %d",
                     summary["actions"]["created"], summary["actions"]["updated"], 
                     summary["actions"]["skipped"], summary["actions"]["conflicts"])
        
        if summary["confidence"]["count"] > 0:
            self.log.info("[metrics] LLM confidence: avg %.3f (%d samples)",
                         summary["confidence"]["average"], summary["confidence"]["count"])
        
        if any(summary["errors"].values()):
            self.log.warning("[metrics] Service errors - Catalog: %d, LCSC: %d, LLM: %d",
                           summary["errors"]["catalog"], summary["errors"]["lcsc"], 
                           summary["errors"]["llm"])
    
    def get_metrics(self) -> ProcessingMetrics:
        """Получить объект метрик."""
        return self.metrics
