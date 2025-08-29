from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class _Product:
    partnumber: str
    name: str
    brand: str
    attrs: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partnumber": self.partnumber,
            "name": self.name,
            "brand": self.brand,
            "attrs": self.attrs,
        }


class CatalogAPIMock:
    """
    Deterministic mock for catalogApp API with simple profiles:
    - happy: single deterministic hit for most inputs
    - missing: always returns empty list
    - conflict: returns 2 candidates with slight differences
    - errorrate10: ~10% requests raise error; otherwise like 'happy'
    - timeout: always raises TimeoutError on any operation
    """

    def __init__(self, profile: str = "happy", seed: int = 42):
        self.profile = profile
        self._rand = random.Random(seed)

    # --- Public API (to match real client minimal surface) ---
    def search_product(self, partnumber: str) -> List[Dict[str, Any]]:
        if self.profile == "timeout":
            raise TimeoutError("catalog search timeout (simulated)")
        if self.profile == "missing":
            return []

        if self.profile == "errorrate10":
            if self._should_error(partnumber, rate=0.10):
                raise RuntimeError("Transient catalog error (simulated)")
            # fallthrough to happy
            return [self._with_id(self._mk_product(partnumber).to_dict(), partnumber)]

        if self.profile == "conflict":
            p1 = self._mk_product(partnumber)
            p2 = self._mk_product(partnumber, alt=True)
            return [
                self._with_id(p1.to_dict(), partnumber),
                self._with_id(p2.to_dict(), partnumber),
            ]

        # default: happy
        return [self._with_id(self._mk_product(partnumber).to_dict(), partnumber)]

    def create_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.profile == "timeout":
            raise TimeoutError("catalog create timeout (simulated)")
        if self.profile == "errorrate10" and self._should_error(str(payload), rate=0.10):
            raise RuntimeError("Transient create error (simulated)")
        created = dict(payload)
        created.setdefault("id", self._stable_id(payload.get("partnumber", "new")))
        created.setdefault("status", "created")
        return created

    def update_product(self, product_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.profile == "timeout":
            raise TimeoutError("catalog update timeout (simulated)")
        if self.profile == "errorrate10" and self._should_error(product_id + str(payload), rate=0.10):
            raise RuntimeError("Transient update error (simulated)")
        updated = dict(payload)
        updated.setdefault("id", product_id)
        updated.setdefault("status", "updated")
        return updated

    # --- Helpers ---
    def _mk_product(self, partnumber: str, alt: bool = False) -> _Product:
        # deterministic pseudo-data based on partnumber
        brand = self._pick_brand(partnumber, alt)
        name = f"{brand} {partnumber}{'-ALT' if alt else ''}"
        attrs = {
            "voltage": self._pick_from(["3.3V", "5V", "12V"], partnumber, salt="v", alt=alt),
            "package": self._pick_from(["SMD", "DIP", "QFN"], partnumber, salt="p", alt=alt),
        }
        return _Product(partnumber=partnumber, name=name, brand=brand, attrs=attrs)

    def _pick_brand(self, partnumber: str, alt: bool) -> str:
        brands = ["TI", "ST", "NXP", "Microchip", "AnalogDevices", "Infineon"]
        return self._pick_from(brands, partnumber, salt="b", alt=alt)

    def _pick_from(self, items: List[str], key: str, salt: str, alt: bool = False) -> str:
        h = hashlib.sha256((key + salt + ("1" if alt else "0")).encode()).digest()
        idx = h[0] % len(items)
        return items[idx]

    def _should_error(self, key: str, rate: float = 0.1) -> bool:
        # stable random by hashing the key to seed a local RNG
        h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        rnd = random.Random(h ^ self._rand.randint(0, 1_000_000))
        return rnd.random() < rate

    def _stable_id(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def _with_id(self, d: Dict[str, Any], partnumber: str) -> Dict[str, Any]:
        enriched = dict(d)
        enriched.setdefault("id", self._stable_id(partnumber))
        return enriched
