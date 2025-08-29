from config import load_config
from import_excel import load_excel
from logger import get_logger, init_logging
from metrics import MetricsCollector
from pipeline import ProcessingPipeline
from reporter import save_report
from services import get_catalog_client, get_lcsc_client, get_llm_client
from validators import DataValidator, SchemaValidator


def process_rows(data, cfg):
    """Общий поток обработки строк данных. Возвращает список результатов.

    Использует рефакторированный ProcessingPipeline с метриками для мониторинга.
    """
    log = get_logger("main")
    metrics = MetricsCollector()
    
    # Валидация схемы данных
    if data:
        columns = set(data[0].keys())
        schema_validator = SchemaValidator()
        schema_result = schema_validator.validate_schema(columns)
        
        if not schema_result.is_valid:
            log.error("[validation] Schema validation failed: %s", schema_result.errors)
            return []
        
        if schema_result.warnings:
            log.warning("[validation] Schema warnings: %s", schema_result.warnings)
    
    # Валидация входных данных: отделяем невалидные строки, добавляем предупреждения
    validator = DataValidator()
    valid_rows, invalid_rows = validator.validate_batch(data)
    log.info("[validation] valid=%s invalid=%s", len(valid_rows), len(invalid_rows))
    
    metrics.set_total_rows(len(data))

    # Инициализация клиентов
    catalog = get_catalog_client(cfg)
    lcsc = None
    llm = None
    # В реальном режиме могут быть не реализованы — поэтому оборачиваем в try
    try:
        lcsc = get_lcsc_client(cfg)
    except Exception:  # pragma: no cover - реальный клиент не реализован
        lcsc = None
    try:
        llm = get_llm_client(cfg)
    except Exception:  # pragma: no cover - реальный клиент не реализован
        llm = None
    log.info("[init] clients: catalog=%s lcsc=%s llm=%s", 
             type(catalog).__name__, 
             type(lcsc).__name__ if lcsc else None, 
             type(llm).__name__ if llm else None)

    # Создание пайплайна обработки
    pipeline = ProcessingPipeline(cfg, catalog, lcsc, llm)
    
    results = []
    # Уже аннотированные невалидные строки просто переносим в отчет
    results.extend(invalid_rows)

    # Обработка валидных строк через пайплайн с метриками
    with metrics.processing_timer():
        for row in valid_rows:
            try:
                processed_row = pipeline.process_single_row(row)
                metrics.add_result(processed_row)
                results.append(processed_row)
            except Exception as e:
                # Любая непредвиденная ошибка — не блокировать партию
                log.error("[main] Unexpected error processing row: %s", e)
                row.update({"status": "error", "reason": f"row_failed: {type(e).__name__}"})
                metrics.add_result(row)
                results.append(row)
    
    # Логирование сводки метрик
    metrics.log_summary()

    return results


def main():
    cfg = load_config()
    logger, _ = init_logging(cfg.log_level)
    logger.info("[startup] Бот 'Исправитель' запущен (level=%s)", cfg.log_level)
    input_path = cfg.input_path or "sample.xlsx"
    logger.info("[startup] input_path=%s", input_path)
    data = load_excel(input_path)
    results = process_rows(data, cfg)
    
    # Передача метрик в отчет
    metrics_collector = MetricsCollector()
    for result in results:
        if result.get("status") != "skip" or result.get("reason", "").startswith("invalid_input"):
            metrics_collector.add_result(result)
    
    report = save_report(results, metrics=metrics_collector.get_metrics())
    if report:
        logger.info("[report] saved to %s", report)
    else:
        logger.error("[report] failed to save")

if __name__ == "__main__":
    main()
