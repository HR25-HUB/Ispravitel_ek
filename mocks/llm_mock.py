from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class LLMResult:
    global_name: str
    local_name: str
    category: str
    attrs: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "global_name": self.global_name,
            "local_name": self.local_name,
            "category": self.category,
            "attrs": self.attrs,
        }


class LLMMock:
    """
    Deterministic mock for LLM normalization/classification.
    - normalize(text): returns normalized names/category/attrs deterministically from input
    - classify(gn_candidates, vn_candidates, text): returns (gn, vn, confidence)
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    # Simplified normalization: derive fields from hashes
    def normalize(self, text: str) -> Dict[str, Any]:
        h = hashlib.sha256(text.encode()).hexdigest()
        global_name = f"GN_{h[:6]}"
        local_name = f"LN_{h[6:12]}"
        category = self._pick_from(["IC", "Resistor", "Capacitor", "Transistor"], h)
        attrs = {
            "confidence": round(int(h[12:14], 16) / 255, 3),
            "tokens": len(text.split()),
        }
        return LLMResult(global_name, local_name, category, attrs).to_dict()

    def classify(self, gn_candidates: list[str], vn_candidates: list[str], text: str) -> Dict[str, Any]:
        h = hashlib.sha256((text + "|" + ",".join(gn_candidates) + ",".join(vn_candidates)).encode()).hexdigest()
        gn = gn_candidates[self._idx(h[:2], len(gn_candidates))] if gn_candidates else ""
        vn = vn_candidates[self._idx(h[2:4], len(vn_candidates))] if vn_candidates else ""
        confidence = round(int(h[4:6], 16) / 255, 3)
        return {"gn": gn, "vn": vn, "confidence": confidence}

    # --- helpers ---
    def _pick_from(self, items: list[str], key: str) -> str:
        idx = int(key[:2], 16) % len(items)
        return items[idx]

    def _idx(self, hex2: str, modulo: int) -> int:
        if modulo <= 0:
            return 0
        return int(hex2, 16) % modulo
