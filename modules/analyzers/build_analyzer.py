
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
OUTPUT_REPORT = OUTPUT_DIR / "build_analysis.json"

BUILD_TIMEOUT_SECONDS = 300
OUTPUT_LIMIT = 12000


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def get_package_manifests(report):
    manifests = []

    for item in report.get("package_json_analysis", []):
        absolute_path = item.get("absolute_path")

        if absolute_path:
            manifests.append(Path(absolute_path).resolve())

    # Avoid processing duplicate manifest paths.
    return list(dict.fromkeys(manifests))


def analyze_build(manifest_path):
    result = {
        "manifest": str(manifest_path),
        "package_directory": str(manifest_path.parent),
        "status": "not_checked",
        "command": None,
        "exit_code": None,
        "duration_seconds": None,
        "stdout": "",
        "stderr": "",
        "error": None
    }

    if not manifest_path.is_file():
        result["status"] = "manifest_missing"
        result["error"] = "package.json was not found."
        return result

    try:
        package_data = load_json(manifest_path)
    except Exception as error:
        result["status"] = "manifest_invalid"
        result["error"] = str(error)
        return result

    scripts = package_data.get("scripts", {})

    result["package_name"] = package_data.get(
        "name", manifest_path.parent.name
    )
    result["available_scripts"] = scripts

    if not isinstance(scripts, dict):
        result["status"] = "invalid_scripts"
        result["error"] = "The scripts field is not a JSON object."
        return result

    if not scripts.get("build"):
        result["status"] = "no_build_script"
        result["error"] = (
            "No build script is defined in this package.json. "
            "This is not necessarily a problem for a Node.js server."
        )
        return result

    node_modules = manifest_path.parent / "node_modules"

    result["command"] = "npm run build"

    if not node_modules.exists():
        result["dependency_note"] = (
            "No local node_modules directory found. "
            "The build may fail if dependencies are not available elsewhere."
        )

    started = time.monotonic()

    try:
        completed = subprocess.run(
            "npm run build",
            cwd=str(manifest_path.parent),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BUILD_TIMEOUT_SECONDS
        )

        duration = round(time.monotonic() - started, 2)

        result["exit_code"] = completed.returncode
        result["duration_seconds"] = duration
        result["stdout"] = completed.stdout[-OUTPUT_LIMIT:]
        result["stderr"] = completed.stderr[-OUTPUT_LIMIT:]

        if completed.returncode == 0:
            result["status"] = "passed"
        else:
            result["status"] = "failed"

    except subprocess.TimeoutExpired as error:
        result["status"] = "timeout"
        result["duration_seconds"] = round(
            time.monotonic() - started, 2
        )
        result["stdout"] = str(error.stdout or "")[-OUTPUT_LIMIT:]
        result["stderr"] = str(error.stderr or "")[-OUTPUT_LIMIT:]
        result["error"] = (
            f"Build exceeded {BUILD_TIMEOUT_SECONDS} seconds."
        )

    except Exception as error:
        result["status"] = "execution_error"
        result["duration_seconds"] = round(
            time.monotonic() - started, 2
        )
        result["error"] = str(error)

    return result


def main():
    if not PROJECT_REPORT.exists():
        raise FileNotFoundError(
            f"Missing project report: {PROJECT_REPORT}"
        )

    report = load_json(PROJECT_REPORT)
    manifests = get_package_manifests(report)

    if not manifests:
        raise ValueError(
            "No package.json paths found in project_report.json"
        )

    results = []

    for index, manifest in enumerate(manifests, start=1):
        print(f"[{index}/{len(manifests)}] Checking: {manifest}")

        results.append(analyze_build(manifest))

    counts = {}

    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1

    output = {
        "project_name": report.get("project_name", "unknown"),
        "analysis_type": "build_analysis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeout_seconds": BUILD_TIMEOUT_SECONDS,
        "packages_checked": len(results),
        "status_counts": counts,
        "results": results,
        "limitations": [
            "Only packages with a build script are built.",
            "A successful build does not guarantee the application runs correctly.",
            "No dependencies are installed automatically.",
            "Build scripts can modify generated files.",
            "Only the last portion of stdout and stderr is retained."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print("\nBuild analysis completed.")
    print(f"Packages checked: {len(results)}")
    print(f"Status counts: {counts}")
    print(f"Report saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Build analysis failed: {error}")