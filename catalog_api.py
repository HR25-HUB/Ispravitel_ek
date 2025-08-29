import random
import time

import requests


class CatalogAPI:
    def __init__(
        self,
        base_url: str = "https://catalogapp/api",
        api_key: str = "test_key",
        *,
        timeout_sec: float = 10.0,
        retries: int = 3,
        backoff_base_ms: int = 100,
        backoff_max_ms: int = 2000,
        backoff_jitter_ms: int = 100,
    ):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout_sec = timeout_sec
        self.retries = max(1, int(retries))
        self.backoff_base_ms = max(0, int(backoff_base_ms))
        self.backoff_max_ms = max(0, int(backoff_max_ms))
        self.backoff_jitter_ms = max(0, int(backoff_jitter_ms))

    def search_product(self, partnumber: str):
        url = f"{self.base_url}/products?partnumber={partnumber}"
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    return resp.json()
                # Non-200 treated as empty result (no raise)
                return []
            except (requests.Timeout, requests.RequestException):  # transient categories
                if attempt < self.retries:
                    # exponential backoff with jitter
                    delay_ms = min(self.backoff_max_ms, self.backoff_base_ms * (2 ** (attempt - 1)))
                    delay_ms += random.randint(0, self.backoff_jitter_ms) if self.backoff_jitter_ms > 0 else 0
                    time.sleep(delay_ms / 1000.0)
                continue
        # After retries, degrade gracefully with empty list
        return []

    def create_product(self, payload: dict):
        url = f"{self.base_url}/products"
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout_sec)
                if resp.status_code in (200, 201):
                    return resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {"status": "ok"}
                # treat as failure but no raise
                return None
            except (requests.Timeout, requests.RequestException):
                if attempt < self.retries:
                    delay_ms = min(self.backoff_max_ms, self.backoff_base_ms * (2 ** (attempt - 1)))
                    delay_ms += random.randint(0, self.backoff_jitter_ms) if self.backoff_jitter_ms > 0 else 0
                    time.sleep(delay_ms / 1000.0)
                continue
        return None

    def update_product(self, product_id: str | int, patch: dict):
        url = f"{self.base_url}/products/{product_id}"
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.patch(url, json=patch, headers=self.headers, timeout=self.timeout_sec)
                if resp.status_code in (200, 204):
                    return True
                return False
            except (requests.Timeout, requests.RequestException):
                if attempt < self.retries:
                    delay_ms = min(self.backoff_max_ms, self.backoff_base_ms * (2 ** (attempt - 1)))
                    delay_ms += random.randint(0, self.backoff_jitter_ms) if self.backoff_jitter_ms > 0 else 0
                    time.sleep(delay_ms / 1000.0)
                continue
        return False
