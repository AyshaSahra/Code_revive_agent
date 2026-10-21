import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, load_config, OUTPUT_DIR

PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
OUTPUT_REPORT = OUTPUT_DIR / "dependency_analysis.json"
CONFIG = load_config("scanner_config.json")


def analyze():
    if not PROJECT_REPORT.is_file():
        raise FileNotFoundError(
            f"Project report not found: {PROJECT_REPORT}"
        )

    report = load_json(PROJECT_REPORT)
    packages = report.get("package_json_analysis", [])

    findings = []
    packages_checked = 0

    if not packages:
        findings.append({
            "type": "no_package_manifests",
            "severity": "info",
            "message": "No package.json manifests were listed in the project report."
        })

    for item in packages:
        raw_path = item.get("absolute_path")

        if not raw_path:
            findings.append({
                "type": "manifest_path_missing",
                "severity": "high",
                "message": "A package manifest has no absolute_path."
            })
            continue

        manifest_path = Path(raw_path)

        if not manifest_path.is_file():
            findings.append({
                "type": "manifest_missing",
                "file": str(manifest_path),
                "severity": "high",
                "message": "The package.json file listed in the report does not exist."
            })
            continue

        try:
            data = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as error:
            findings.append({
                "type": "manifest_invalid",
                "file": str(manifest_path),
                "severity": "high",
                "message": f"Could not read valid JSON: {error}"
            })
            continue

        packages_checked += 1

        # Check dependency section formats.
        for section in CONFIG["dependency_sections"]:
            if section in data and not isinstance(data[section], dict):
                findings.append({
                    "type": "invalid_dependency_section",
                    "file": str(manifest_path),
                    "section": section,
                    "severity": "high",
                    "message": f"{section} should be a JSON object."
                })

        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            findings.append({
                "type": "invalid_scripts_section",
                "file": str(manifest_path),
                "severity": "high",
                "message": "The scripts section should be a JSON object."
            })
            scripts = {}

        folder = manifest_path.parent
        relative_folder = str(folder)

        # A server entry point with no start script is a warning,
        # not proof that the application cannot run.
        server_entry_exists = any(
            (folder / filename).is_file()
            for filename in (
                "server.js", "app.js", "index.js", "server.ts"
            )
        )

        if server_entry_exists and "start" not in scripts:
            findings.append({
                "type": "missing_start_script",
                "file": str(manifest_path),
                "severity": "medium",
                "message": (
                    "A possible server entry file exists, but package.json "
                    "does not define a start script."
                )
            })

        # A build script is commonly useful for client applications.
        package_name = data.get("name", manifest_path.parent.name).lower()
        
        client_indicators = CONFIG.get("client_indicators", [])
        is_client = (
            "client" in folder.parts
            or "frontend" in folder.parts
            or any(indicator in data.get("dependencies", {}) for indicator in client_indicators)
        )

        if is_client and "build" not in scripts:
            findings.append({
                "type": "missing_build_script",
                "file": str(manifest_path),
                "severity": "low",
                "message": (
                    "This package looks like a client application, "
                    "but no build script was found."
                )
            })

        # A lockfile is useful for reproducible installs, but its absence
        # alone does not mean the project is broken.
        found_lockfiles = [
            name for name in CONFIG["lockfiles"]
            if (folder / name).is_file()
        ]

        if not found_lockfiles:
            findings.append({
                "type": "lockfile_not_found",
                "file": str(manifest_path),
                "severity": "low",
                "message": (
                    "No common package lockfile was found beside this manifest."
                )
            })

        print(f"Checked: {manifest_path}")

    result = {
        "project_name": report.get("project_name"),
        "package_manifests_checked": packages_checked,
        "findings_count": len(findings),
        "findings": findings,
        "limitations": [
            "This module does not install dependencies or query registries.",
            "It does not establish whether a dependency version is outdated or vulnerable.",
            "Missing scripts and lockfiles are warnings, not automatic proof of failure.",
            "Workspace and monorepo conventions may require project-specific rules."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_REPORT.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)

    print(f"\nPackages checked: {packages_checked}")
    print(f"Findings: {len(findings)}")
    print(f"Saved: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        analyze()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(f"Dependency analysis failed: {error}")