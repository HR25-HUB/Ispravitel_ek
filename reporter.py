import json
from pathlib import Path

import pandas as pd

from logger import generate_run_id, get_logger
from metrics import ProcessingMetrics


def save_report(data: list, filename: str = None, metrics: ProcessingMetrics = None):
    log = get_logger("reporter")
    if not filename:
        run_id = generate_run_id()
        # Ensure reports directory exists and save into it by default
        reports_dir = Path("reports")
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Directory creation failure should not block report creation; fallback to current directory
            reports_dir = Path(".")
        filename = str(reports_dir / f"report_{run_id}.xlsx")
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

            # Enhanced metrics with ProcessingMetrics integration
            sections = []
            try:
                total = len(df)
                sections.append(pd.DataFrame({"metric": ["total_rows"], "value": [total]}))

                # Add ProcessingMetrics summary if available
                if metrics:
                    summary = metrics.get_summary()
                    
                    # Performance metrics
                    perf_metrics = pd.DataFrame({
                        "metric": ["processing_time_sec", "avg_row_time_sec", "success_rate_percent"],
                        "value": [summary["processing_time"], summary["avg_row_time"], summary["success_rate"]]
                    })
                    sections.append(perf_metrics)
                    
                    # Action metrics
                    action_metrics = pd.DataFrame({
                        "metric": ["created", "updated", "skipped", "conflicts"],
                        "value": [summary["actions"]["created"], summary["actions"]["updated"], 
                                 summary["actions"]["skipped"], summary["actions"]["conflicts"]]
                    })
                    sections.append(action_metrics)
                    
                    # Error metrics
                    error_metrics = pd.DataFrame({
                        "metric": ["catalog_errors", "lcsc_errors", "llm_errors"],
                        "value": [summary["errors"]["catalog"], summary["errors"]["lcsc"], summary["errors"]["llm"]]
                    })
                    sections.append(error_metrics)
                    
                    # Confidence metrics
                    if summary["confidence"]["count"] > 0:
                        conf_metrics = pd.DataFrame({
                            "metric": ["avg_confidence", "confidence_samples"],
                            "value": [summary["confidence"]["average"], summary["confidence"]["count"]]
                        })
                        sections.append(conf_metrics)

                # Standard counts from data
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
