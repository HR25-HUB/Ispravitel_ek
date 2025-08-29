import random
import time
from typing import Any

import requests


class LLMClientReal:
    """
    Простой REST‑клиент к LLM‑сервису (например, прокси к Coze/OpenAI).

    Контракты по умолчанию:
    POST {base_url}/normalize {"text": str}
      -> 200 OK: {"local_name": str, "attrs": {..}}
    POST {base_url}/classify {"text": str, "gn_candidates": [..], "vn_candidates": [..]}
      -> 200 OK: {"gn": str, "vn": str, "confidence": float}
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_sec: float = 15.0,
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
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        return data
                    return {}
                return {}
            except (requests.Timeout, requests.RequestException):
                if attempt < self.retries:
                    delay_ms = min(self.backoff_max_ms, self.backoff_base_ms * (2 ** (attempt - 1)))
                    delay_ms += random.randint(0, self.backoff_jitter_ms) if self.backoff_jitter_ms > 0 else 0
                    time.sleep(delay_ms / 1000.0)
                continue
        return {}

    def normalize(self, text: str) -> dict[str, Any]:
        return self._post("/normalize", {"text": text})

    def classify(self, gn_candidates: list[str], vn_candidates: list[str], text: str) -> dict[str, Any]:
        return self._post("/classify", {
            "text": text,
            "gn_candidates": gn_candidates,
            "vn_candidates": vn_candidates,
        })
