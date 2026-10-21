import json
import os
import subprocess
import time
import threading
import queue
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, load_config, OUTPUT_DIR

PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
OUTPUT_REPORT = OUTPUT_DIR / "runtime_analysis.json"
CONFIG = load_config("scanner_config.json")


def discover_manifests(report):
    manifests = []

    for item in report.get("package_json_analysis", []):
        raw_path = item.get("absolute_path")
        if raw_path:
            path = Path(raw_path).resolve()
            if path not in manifests:
                manifests.append(path)

    return manifests


def run_start_script(manifest_path):
    result = {
        "manifest": str(manifest_path),
        "package_directory": str(manifest_path.parent),
        "status": "not_checked",
        "command": "npm run start",
        "duration_seconds": None,
        "exit_code": None,
        "output": "",
        "error": None
    }

    if not manifest_path.is_file():
        result["status"] = "manifest_missing"
        result["error"] = "package.json was not found."
        return result

    try:
        package = load_json(manifest_path)
    except Exception as error:
        result["status"] = "manifest_invalid"
        result["error"] = str(error)
        return result

    scripts = package.get("scripts", {})
    result["package_name"] = package.get(
        "name", manifest_path.parent.name
    )

    if not isinstance(scripts, dict):
        result["status"] = "invalid_scripts"
        result["error"] = "The scripts field must be an object."
        return result

    if not scripts.get("start"):
        result["status"] = "no_start_script"
        result["error"] = "No start script is defined."
        return result

    print(f"Starting smoke test: {manifest_path.parent}", flush=True)
    started = time.monotonic()
    captured = []
    output_queue = queue.Queue()
    process = None
    
    startup_window = CONFIG["limits"]["startup_window_seconds"]
    output_limit = CONFIG["limits"]["output_limit"]

    try:
        process = subprocess.Popen(
            "npm run start",
            cwd=str(manifest_path.parent),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

        def read_output():
            try:
                for line in process.stdout:
                    output_queue.put(line)
            finally:
                output_queue.put(None)

        threading.Thread(target=read_output, daemon=True).start()

        output_finished = False
        deadline = started + startup_window

        while time.monotonic() < deadline and not output_finished:
            if process.poll() is not None and output_queue.empty():
                break

            try:
                line = output_queue.get(timeout=0.2)
                if line is None:
                    output_finished = True
                else:
                    print(line, end="", flush=True)
                    captured.append(line)

                    while sum(map(len, captured)) > output_limit:
                        captured.pop(0)
            except queue.Empty:
                continue

        # Drain any output already queued.
        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break

            if line is None:
                output_finished = True
            else:
                captured.append(line)
                while sum(map(len, captured)) > output_limit:
                    captured.pop(0)

        exit_code = process.poll()

        if exit_code is not None:
            result["exit_code"] = exit_code
            result["status"] = (
                "exited_successfully" if exit_code == 0
                else "startup_failed"
            )
        else:
            result["status"] = "survived_startup_window"
            result["note"] = (
                "The process stayed alive during the smoke test. "
                "This does not prove that endpoints or features work."
            )

    except Exception as error:
        result["status"] = "execution_error"
        result["error"] = str(error)

    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        result["duration_seconds"] = round(
            time.monotonic() - started, 2
        )
        result["output"] = "".join(captured)[-output_limit:]

    return result


def main():
    if not PROJECT_REPORT.exists():
        raise FileNotFoundError(
            f"Missing report: {PROJECT_REPORT}"
        )

    report = load_json(PROJECT_REPORT)
    manifests = discover_manifests(report)

    if not manifests:
        raise ValueError(
            "No package manifests found in project_report.json"
        )

    results = []

    for index, manifest in enumerate(manifests, start=1):
        print(f"\n[{index}/{len(manifests)}] Runtime check: {manifest}")
        results.append(run_start_script(manifest))

    status_counts = {}
    for result in results:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    output = {
        "project_name": report.get("project_name", "unknown"),
        "analysis_type": "runtime_analysis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "startup_window_seconds": CONFIG["limits"]["startup_window_seconds"],
        "packages_checked": len(results),
        "status_counts": status_counts,
        "results": results,
        "limitations": [
            "A process surviving the startup window is not proof of correctness.",
            "HTTP endpoints are not tested by this smoke test.",
            "Database connectivity and feature behavior are not verified.",
            "Start scripts execute project-defined commands."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print("\nRuntime analysis completed.")
    print(f"Status counts: {status_counts}")
    print(f"Report saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Runtime analysis failed: {error}")