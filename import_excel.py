import math

import pandas as pd


def _to_str(v) -> str:
    """Normalize cell value to a trimmed string. NaN/None -> empty string."""
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()

def load_excel(path: str):
    try:
        df = pd.read_excel(path)
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Ошибка загрузки Excel: {e}")
        return []


def validate_input(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Validate and normalize input rows.

    Rules:
    - partnumber: required, deduplicate by case-insensitive value; duplicates beyond first are invalid.
    - brand: recommended; if missing -> add warning but still process.
    - Normalize typical fields to strings: partnumber, brand, gn, vn, external_id.

    Returns (valid_rows, invalid_rows). Each row may be annotated with:
    - warnings: semicolon-separated string of validation warnings
    - errors: semicolon-separated string of validation errors
    - status/action/reason for invalid rows (set to skip/invalid_input:*)
    """
    seen_parts: set[str] = set()
    valid: list[dict] = []
    invalid: list[dict] = []

    for row in rows:
        # Work on a shallow copy to avoid mutating caller's object if they reuse it
        r = dict(row)

        # Normalize common fields
        pn = _to_str(r.get("partnumber", ""))
        brand = _to_str(r.get("brand", ""))
        r["partnumber"] = pn
        r["brand"] = brand
        if "gn" in r:
            r["gn"] = _to_str(r.get("gn"))
        if "vn" in r:
            r["vn"] = _to_str(r.get("vn"))
        if "external_id" in r:
            r["external_id"] = _to_str(r.get("external_id"))

        warnings: list[str] = []
        errors: list[str] = []

        # Required: partnumber
        if not pn:
            errors.append("validation:missing_partnumber")
            r.update({
                "status": "skip",
                "action": "skip",
                "reason": "invalid_input:missing_partnumber",
            })
            r["errors"] = ";".join(errors)
            r["warnings"] = ";".join(warnings)
            invalid.append(r)
            continue

        # Recommended: brand
        if not brand:
            warnings.append("validation:missing_brand")

        # Duplicates by partnumber (case-insensitive)
        key = pn.lower()
        if key in seen_parts:
            errors.append("validation:duplicate_partnumber")
            r.update({
                "status": "skip",
                "action": "skip",
                "reason": "invalid_input:duplicate_partnumber",
            })
            r["errors"] = ";".join(errors)
            r["warnings"] = ";".join(warnings)
            invalid.append(r)
            continue
        seen_parts.add(key)

        # Attach annotations for valid rows as well (main/reporting expects strings)
        if warnings:
            r["warnings"] = ";".join(warnings)
        if errors:
            r["errors"] = ";".join(errors)

        valid.append(r)

    return valid, invalid
