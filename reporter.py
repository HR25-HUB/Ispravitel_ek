import json

import pandas as pd

from logger import generate_run_id, get_logger


def save_report(data: list, filename: str = None):
    log = get_logger("reporter")
    if not filename:
        run_id = generate_run_id()
        filename = f"report_{run_id}.xlsx"
    try:
        df = pd.DataFrame(data)
        # Ensure attrs_norm is a JSON string when present
        if "attrs_norm" in df.columns:
            def _to_json(v):
                if isinstance(v, str):
                    return v
                try:
                    return json.dumps(v if v is not None else {}, ensure_ascii=False)
                except Exception:
                    return ""
            df["attrs_norm"] = df["attrs_norm"].map(_to_json)

        # Preferred column order for readability
        preferred = [
            "external_id",
            "partnumber",
            "brand",
            "gn",
            "vn",
            "found_in_catalog",
            "action",
            "status",
            "reason",
            "confidence",
            "attrs_norm",
            "errors",
            "warnings",
        ]
        ordered = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
        df = df[ordered]

        # Write data and metrics to separate sheets
        try:
            writer = pd.ExcelWriter(filename, engine="xlsxwriter")
        except Exception:
            # Fallback to openpyxl if xlsxwriter is not available
            writer = pd.ExcelWriter(filename, engine="openpyxl")
        with writer as writer:
            df.to_excel(writer, index=False, sheet_name="data")

            # Basic metrics
            sections = []
            try:
                total = len(df)
                sections.append(pd.DataFrame({"metric": ["total_rows"], "value": [total]}))

                if "status" in df.columns:
                    status_counts = df["status"].value_counts(dropna=False).rename_axis("status").reset_index(name="count")
                    status_counts.insert(0, "section", "status_counts")
                    sections.append(status_counts)
                if "action" in df.columns:
                    action_counts = df["action"].value_counts(dropna=False).rename_axis("action").reset_index(name="count")
                    action_counts.insert(0, "section", "action_counts")
                    sections.append(action_counts)
                if "reason" in df.columns:
                    reason_counts = df["reason"].value_counts(dropna=False).rename_axis("reason").reset_index(name="count")
                    reason_counts.insert(0, "section", "reason_counts")
                    sections.append(reason_counts)

                metrics_df = pd.concat(sections, ignore_index=True) if sections else pd.DataFrame({"metric": [], "value": []})
            except Exception as e:  # pragma: no cover - defensive metrics build
                log.warning("[report] metrics build failed: %s", e)
                metrics_df = pd.DataFrame({"metric": [], "value": []})

            metrics_df.to_excel(writer, index=False, sheet_name="metrics")

        log.info("[report] saved: %s", filename)
        return filename
    except Exception as e:
        log.error("[report] save failed: %s", e)
        return None
