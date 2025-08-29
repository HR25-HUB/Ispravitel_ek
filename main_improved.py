"""Улучшенная версия main.py с использованием новых модулей."""
from __future__ import annotations

from config import load_config
from import_excel import load_excel
from logger import get_logger, init_logging
from metrics import MetricsCollector
from pipeline import ProcessingPipeline
from reporter import save_report
from services import get_catalog_client, get_lcsc_client, get_llm_client
from validators import DataValidator, SchemaValidator


def process_rows_improved(data: list, cfg):
    """Улучшенная версия обработки строк с метриками и валидацией."""
    log = get_logger("main")
    metrics = MetricsCollector()
    
    # Валидация схемы
    if data:
        columns = set(data[0].keys())
        schema_validator = SchemaValidator()
        schema_result = schema_validator.validate_schema(columns)
        
        if not schema_result.is_valid:
            log.error("[validation] Schema validation failed: %s", schema_result.errors)
            return []
        
        if schema_result.warnings:
            log.warning("[validation] Schema warnings: %s", schema_result.warnings)
    
    # Валидация данных
    validator = DataValidator()
    valid_rows, invalid_rows = validator.validate_batch(data)
    
    log.info("[validation] valid=%s invalid=%s", len(valid_rows), len(invalid_rows))
    metrics.set_total_rows(len(data))
    
    # Инициализация клиентов
    catalog = get_catalog_client(cfg)
    lcsc = None
    llm = None
    
    try:
        lcsc = get_lcsc_client(cfg)
    except Exception:
        lcsc = None
    
    try:
        llm = get_llm_client(cfg)
    except Exception:
        llm = None
    
    log.info("[init] clients: catalog=%s lcsc=%s llm=%s", 
             type(catalog).__name__, 
             type(lcsc).__name__ if lcsc else None, 
             type(llm).__name__ if llm else None)
    
    # Создание пайплайна
    pipeline = ProcessingPipeline(cfg, catalog, lcsc, llm)
    
    results = []
    results.extend(invalid_rows)  # Добавляем невалидные строки
    
    # Обработка валидных строк с метриками
    with metrics.processing_timer():
        for row in valid_rows:
            try:
                processed_row = pipeline.process_single_row(row)
                metrics.add_result(processed_row)
                results.append(processed_row)
            except Exception as e:
                log.error("[pipeline] Unexpected error processing row: %s", e)
                row.update({
                    "status": "error", 
                    "reason": f"row_failed: {type(e).__name__}",
                    "errors": f"pipeline:{type(e).__name__}"
                })
                results.append(row)
    
    # Логирование метрик
    metrics.log_summary()
    
    return results


def main():
    """Главная функция с улучшенной обработкой."""
    cfg = load_config()
    logger, _ = init_logging(cfg.log_level)
    logger.info("[startup] Бот 'Исправитель' запущен (улучшенная версия, level=%s)", cfg.log_level)
    
    input_path = cfg.input_path or "sample.xlsx"
    logger.info("[startup] input_path=%s", input_path)
    
    try:
        data = load_excel(input_path)
        if not data:
            logger.error("[startup] No data loaded from %s", input_path)
            return
        
        results = process_rows_improved(data, cfg)
        
        if results:
            report = save_report(results)
            if report:
                logger.info("[report] saved to %s", report)
            else:
                logger.error("[report] failed to save")
        else:
            logger.warning("[main] No results to save")
            
    except Exception as e:
        logger.error("[main] Fatal error: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
