import random
import time
from typing import Any

import requests


class LCSCClientReal:
    """
    Простой HTTP‑клиент для LCSC через настраиваемый REST‑ендпоинт.
    Предполагается, что бизнес предоставит прокси‑API к LCSC.

    Ожидаемый контракт поиска:
    GET {base_url}/search?q={partnumber}
      -> 200 OK: [{"partnumber": str, "brand": str, "category": str, "attrs": {..}, "datasheet_url": str}]
      -> иначе: []
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_sec: float = 10.0,
        retries: int = 3,
        backoff_base_ms: int = 100,
        backoff_max_ms: int = 2000,
        backoff_jitter_ms: int = 100,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.retries = max(1, int(retries))
        self.backoff_base_ms = max(0, int(backoff_base_ms))
        self.backoff_max_ms = max(0, int(backoff_max_ms))
        self.backoff_jitter_ms = max(0, int(backoff_jitter_ms))
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def search(self, partnumber: str) -> list[dict[str, Any]]:
        url = f"{self.base_url}/search"
        params = {"q": partnumber}
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.get(url, params=params, headers=self.headers, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    return []
                return []
            except (requests.Timeout, requests.RequestException):
                if attempt < self.retries:
                    delay_ms = min(self.backoff_max_ms, self.backoff_base_ms * (2 ** (attempt - 1)))
                    delay_ms += random.randint(0, self.backoff_jitter_ms) if self.backoff_jitter_ms > 0 else 0
                    time.sleep(delay_ms / 1000.0)
                continue
        return []
