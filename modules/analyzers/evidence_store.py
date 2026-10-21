import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, load_config, OUTPUT_DIR

OUTPUT_REPORT = OUTPUT_DIR / "evidence_store.json"
CONFIG = load_config("scanner_config.json")


def first_value(item, keys, default=None):
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def make_evidence(source_name, item, category):
    """Convert one analyzer finding/result into a common record."""

    file_path = first_value(
        item,
        ["file", "file_path", "path", "manifest", "package_directory"]
    )

    line = first_value(item, ["line", "line_number"])
    rule = first_value(item, ["rule", "code", "check"])
    severity = first_value(item, ["severity", "level"], "info")
    status = first_value(item, ["status", "result"])
    message = first_value(
        item,
        ["message", "error", "description", "note"],
        "Detection result recorded."
    )
    evidence_text = first_value(
        item,
        ["evidence", "snippet", "output", "stderr", "stdout"],
        ""
    )

    record = {
        "source_analyzer": source_name,
        "category": category,
        "severity": str(severity).lower(),
        "status": status,
        "rule": rule,
        "file": file_path,
        "line": line,
        "message": str(message),
        "evidence": str(evidence_text)[:2000]
    }

    # Stable ID so the same finding can be recognized across runs.
    identity = json.dumps(record, sort_keys=True, ensure_ascii=False)
    record["evidence_id"] = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16]

    return record


def extract_records(data, source_name):
    records = []

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
            return

        if not isinstance(value, dict):
            return

        # Individual code findings from source/import/static analyzers.
        has_finding_fields = (
            "rule" in value
            or (
                "severity" in value
                and any(key in value for key in ("message", "file", "file_path"))
            )
        )

        # Build/runtime/dependency package-level results.
        has_result_fields = (
            "status" in value
            and any(
                key in value
                for key in ("error", "exit_code", "output", "duration_seconds")
            )
        )

        if has_finding_fields or has_result_fields:
            records.append(
                make_evidence(source_name, value, source_name)
            )

        # Continue into nested structures such as findings and results.
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    visit(data)
    return records


def main():
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(
            f"Output directory not found: {OUTPUT_DIR}"
        )

    evidence_records = []
    report_status = {}

    for source_name, filename in CONFIG["input_reports"].items():
        report_path = OUTPUT_DIR / filename

        if not report_path.is_file():
            report_status[source_name] = {
                "status": "missing",
                "file": filename
            }
            print(f"Skipping missing report: {filename}")
            continue

        try:
            data = load_json(report_path)
        except Exception as error:
            report_status[source_name] = {
                "status": "invalid_json",
                "file": filename,
                "error": str(error)
            }
            print(f"Could not read {filename}: {error}")
            continue

        records = extract_records(data, source_name)
        evidence_records.extend(records)

        report_status[source_name] = {
            "status": "loaded",
            "file": filename,
            "records_extracted": len(records)
        }

        print(f"Loaded {filename}: {len(records)} records")

    # Deduplicate identical evidence IDs while preserving order.
    unique_records = []
    seen_ids = set()

    for record in evidence_records:
        evidence_id = record["evidence_id"]
        if evidence_id not in seen_ids:
            seen_ids.add(evidence_id)
            unique_records.append(record)

    severity_counts = {}
    for record in unique_records:
        severity = record["severity"]
        severity_counts[severity] = (
            severity_counts.get(severity, 0) + 1
        )

    output = {
        "project_name": "unknown",
        "store_type": "local_json",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": report_status,
        "total_records_before_deduplication": len(evidence_records),
        "total_evidence_records": len(unique_records),
        "severity_counts": severity_counts,
        "evidence": unique_records
    }

    # Use the project name from the project report if available.
    project_report = OUTPUT_DIR / "project_report.json"
    if project_report.is_file():
        try:
            project_data = load_json(project_report)
            output["project_name"] = project_data.get(
                "project_name", "unknown"
            )
        except Exception:
            pass

    OUTPUT_REPORT.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print("\nEvidence store created.")
    print(f"Unique evidence records: {len(unique_records)}")
    print(f"Severity counts: {severity_counts}")
    print(f"Saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Evidence store failed: {error}")