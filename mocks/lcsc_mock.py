from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class _LCSCItem:
    partnumber: str
    brand: str
    category: str
    attrs: Dict[str, Any]
    datasheet_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partnumber": self.partnumber,
            "brand": self.brand,
            "category": self.category,
            "attrs": self.attrs,
            "datasheet_url": self.datasheet_url,
        }


class LCSCMock:
    """
    Deterministic mock for LCSC web search by partnumber.
    Profiles:
      - happy: returns a single deterministic candidate
      - missing: returns empty list
      - conflict: returns two candidates with slightly different brand/category
      - errorrate10: ~10% raises, otherwise like 'happy'
      - timeout: always raises TimeoutError
    """

    def __init__(self, profile: str = "happy", seed: int = 42):
        self.profile = profile
        self._rand = random.Random(seed)

    def search(self, partnumber: str) -> List[Dict[str, Any]]:
        if self.profile == "timeout":
            raise TimeoutError("LCSC search timeout (simulated)")
        if self.profile == "missing":
            return []

        if self.profile == "errorrate10":
            if self._should_error(partnumber, rate=0.10):
                raise RuntimeError("Transient LCSC error (simulated)")
            return [self._mk_item(partnumber).to_dict()]

        if self.profile == "conflict":
            return [
                self._mk_item(partnumber).to_dict(),
                self._mk_item(partnumber, alt=True).to_dict(),
            ]

        return [self._mk_item(partnumber).to_dict()]

    # --- helpers ---
    def _mk_item(self, partnumber: str, alt: bool = False) -> _LCSCItem:
        brand = self._pick_from(["TI", "ST", "NXP", "Microchip"], partnumber, salt="b", alt=alt)
        category = self._pick_from(["IC", "Resistor", "Capacitor", "Transistor"], partnumber, salt="c", alt=alt)
        attrs = {
            "power": self._pick_from(["0.25W", "0.5W", "1W"], partnumber, salt="p", alt=alt),
            "tolerance": self._pick_from(["1%", "5%", "10%"], partnumber, salt="t", alt=alt),
        }
        ds = f"https://datasheets.example/{self._stable_id(partnumber)}.pdf"
        return _LCSCItem(partnumber=partnumber, brand=brand, category=category, attrs=attrs, datasheet_url=ds)

    def _pick_from(self, items: List[str], key: str, *, salt: str, alt: bool = False) -> str:
        h = hashlib.sha256((key + salt + ("1" if alt else "0")).encode()).digest()
        idx = h[0] % len(items)
        return items[idx]

    def _stable_id(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def _should_error(self, key: str, rate: float = 0.1) -> bool:
        h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        rnd = random.Random(h ^ self._rand.randint(0, 1_000_000))
        return rnd.random() < rate
