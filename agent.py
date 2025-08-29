import subprocess
import time

from config import load_config
from logger import get_logger, init_logging


def job():
    log = get_logger("agent")
    log.info("[agent] запуск обработки Excel")
    try:
        subprocess.run(["python", "main.py"], check=True)
        log.info("[agent] обработка завершена успешно")
    except subprocess.CalledProcessError as exc:
        log.error("[agent] ошибка запуска main.py: rc=%s", exc.returncode)


def setup_schedule(schedule_obj, when: str) -> None:
    """Настраивает ежедневный запуск job() на указанное время HH:MM.

    Выделено в отдельную функцию для удобства тестирования.
    """
    schedule_obj.every().day.at(when).do(job)


def _run_pending_loop(schedule_obj, iterations: int | None = None, sleep_seconds: int = 30, sleep_fn=time.sleep) -> None:
    """Запускает цикл выполнения запланированных задач.

    iterations=None — бесконечный цикл.
    iterations=N — выполнить N итераций (для тестов), между итерациями sleep_seconds.
    """
    count = 0
    while True:
        schedule_obj.run_pending()
        if iterations is not None:
            count += 1
            if count >= iterations:
                break
        sleep_fn(sleep_seconds)


def run_agent():
    import schedule  # lazy import to keep tests independent from this dependency
    # План: запускать раз в день в 03:00
    cfg = load_config()
    setup_schedule(schedule, cfg.agent_schedule)
    logger, _ = init_logging(cfg.log_level)
    logger.info("[agent] запущен. Расписание=%s. Ожидание задач...", cfg.agent_schedule)
    _run_pending_loop(schedule)

if __name__ == "__main__":
    run_agent()
