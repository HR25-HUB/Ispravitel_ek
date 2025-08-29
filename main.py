import json
import random
import time

from config import load_config
from import_excel import load_excel, validate_input
from logger import get_logger, init_logging
from reporter import save_report
from services import get_catalog_client, get_lcsc_client, get_llm_client


def process_rows(data, cfg):
    """Общий поток обработки строк данных. Возвращает список результатов.

    Использует фабрики клиентов из services.py и конфиг cfg.
    """
    log = get_logger("pipeline")
    # Валидация входных данных: отделяем невалидные строки, добавляем предупреждения
    valid_rows, invalid_rows = validate_input(data)
    log.info("[validation] valid=%s invalid=%s", len(valid_rows), len(invalid_rows))

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
    log.info("[init] clients: catalog=%s lcsc=%s llm=%s", type(catalog).__name__, type(lcsc).__name__ if lcsc else None, type(llm).__name__ if llm else None)

    results = []
    # Уже аннотированные невалидные строки просто переносим в отчет
    results.extend(invalid_rows)

    def _retry(callable_, *args, attempts: int = 3, errors_list: list | None = None, tag: str = ""):
        last_exc = None
        for i in range(1, attempts + 1):
            try:
                return callable_(*args)
            except Exception as e:  # pragma: no cover - behavior depends on mock profiles
                last_exc = e
                if errors_list is not None:
                    errors_list.append(f"{tag}:{type(e).__name__}:attempt{i}")
                if i < attempts:
                    # exponential backoff with jitter from config
                    base = getattr(cfg, "backoff_base_ms", 100)
                    max_ms = getattr(cfg, "backoff_max_ms", 2000)
                    jitter = getattr(cfg, "backoff_jitter_ms", 100)
                    delay_ms = min(max_ms, base * (2 ** (i - 1)))
                    delay_ms += random.randint(0, jitter) if jitter > 0 else 0
                    time.sleep(delay_ms / 1000.0)
        if last_exc:
            raise last_exc

    for row in valid_rows:
        try:
            part = str(row.get("partnumber", "")).strip()
            brand = str(row.get("brand", "")).strip()

            decision = {"action": "skip", "reason": "no_partnumber"}
            enriched = {}
            found_flag = False
            confidence_val = None
            attrs_norm: dict = {}
            errors: list[str] = []

            if not part:
                row.update({"status": decision["action"], "reason": decision["reason"]})
                results.append(row)
                continue

            # 1) Поиск в catalogApp (с ретраями)
            try:
                found = _retry(catalog.search_product, part, attempts=3, errors_list=errors, tag="catalog_search")
            except Exception:
                found = []

            if found:
                # Простейшая логика: если бренд отличается — готовим обновление
                best = found[0]
                found_flag = True
                if brand and best.get("brand") and best.get("brand") != brand:
                    if hasattr(catalog, "update_product"):
                        try:
                            _retry(catalog.update_product, best.get("id"), {"brand": brand}, attempts=3, errors_list=errors, tag="catalog_update")  # type: ignore[attr-defined]
                            decision = {"action": "update", "reason": "brand_mismatch"}
                            log.info("[catalog] update id=%s brand=%s->%s", best.get("id"), best.get("brand"), brand)
                        except Exception:
                            decision = {"action": "conflict", "reason": "update_failed"}
                    else:
                        decision = {"action": "conflict", "reason": "update_not_supported"}
                else:
                    decision = {"action": "skip", "reason": "already_present"}
            else:
                # 2) Фоллбек к LCSC
                candidates = []
                # Маркируем как не найдено в каталоге — может быть перезаписано более строгими причинами (напр., low_confidence)
                decision = {"action": "skip", "reason": "not_found"}
                if lcsc is not None:
                    try:
                        candidates = _retry(lcsc.search, part, attempts=3, errors_list=errors, tag="lcsc_search")
                        log.info("[lcsc] candidates=%s for part=%s", len(candidates), part)
                    except Exception:
                        candidates = []

                # 3) Нормализация/классификация
                norm = {}
                if llm is not None:
                    try:
                        text = f"{part} {brand}".strip()
                        norm = llm.normalize(text)
                        attrs_norm = norm.get("attrs") or {}
                        classif = llm.classify(["ГН1", "ГН2", "ГН3"], ["ВН1", "ВН2", "ВН3"], text)
                        confidence_val = classif.get("confidence")
                        if (confidence_val or 0.0) < cfg.confidence_threshold:
                            decision = {"action": "skip", "reason": "low_confidence"}
                            log.info("[llm] low_confidence=%.3f threshold=%.3f part=%s", confidence_val or 0.0, cfg.confidence_threshold, part)
                        else:
                            enriched.update({"gn": classif.get("gn"), "vn": classif.get("vn")})
                            log.info("[llm] ok gn=%s vn=%s conf=%.3f", classif.get("gn"), classif.get("vn"), confidence_val or 0.0)
                    except Exception as e:
                        errors.append(f"llm:{type(e).__name__}")

                # 4) Создание в каталоге — только если поддерживается мок-клиентом
                # Не создаем при низкой уверенности
                if (
                    decision["action"] == "skip"
                    and decision.get("reason") == "not_found"
                    and hasattr(catalog, "create_product")
                ):
                    try:
                        payload = {
                            "partnumber": part,
                            "name": norm.get("local_name") or part,
                            "brand": brand or (candidates[0]["brand"] if candidates else ""),
                            "attrs": attrs_norm or {},
                        }
                        _retry(catalog.create_product, payload, attempts=3, errors_list=errors, tag="catalog_create")  # type: ignore[attr-defined]
                        decision = {"action": "create", "reason": "not_found"}
                        log.info("[catalog] create part=%s brand=%s", part, payload.get("brand"))
                    except Exception:
                        decision = {"action": "conflict", "reason": "create_failed"}

            # Записываем результат строки
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
            results.append(row)
        except Exception as e:
            # Любая непредвиденная ошибка — не блокировать партию
            row.update({"status": "error", "reason": f"row_failed: {type(e).__name__}"})
            results.append(row)

    return results


def main():
    cfg = load_config()
    logger, _ = init_logging(cfg.log_level)
    logger.info("[startup] Бот 'Исправитель' запущен (level=%s)", cfg.log_level)
    input_path = cfg.input_path or "sample.xlsx"
    logger.info("[startup] input_path=%s", input_path)
    data = load_excel(input_path)
    results = process_rows(data, cfg)
    report = save_report(results)
    if report:
        logger.info("[report] saved to %s", report)
    else:
        logger.error("[report] failed to save")

if __name__ == "__main__":
    main()
