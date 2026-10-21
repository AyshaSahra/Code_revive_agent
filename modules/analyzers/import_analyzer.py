
import json
import os
import re
from pathlib import Path


# The Code Revive Agent project's own output folder
BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"

PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
SOURCE_REPORT = OUTPUT_DIR / "source_analysis.json"
OUTPUT_REPORT = OUTPUT_DIR / "import_analysis.json"

IGNORED_DIRS = {
    "node_modules", ".git", "dist", "build",
    ".next", "coverage", "venv", ".venv"
}

EXTENSIONS = [
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".json"
]

NODE_BUILTINS = {
    "assert", "buffer", "child_process", "crypto",
    "events", "fs", "http", "https", "module",
    "os", "path", "process", "stream", "url",
    "util", "zlib", "timers", "worker_threads",
    "net", "dns", "readline", "tty", "querystring",
    "string_decoder", "punycode", "console"
}

IMPORT_PATTERN = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(|\brequire\s*\()\s*
        ['"]([^'"]+)['"]
        |
        ^\s*import\s*['"]([^'"]+)['"]""",
    re.MULTILINE | re.VERBOSE
)


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def find_project_root(project_report):
    """Find the common parent of all reported package.json directories."""
    packages = project_report.get("package_json_analysis", [])

    package_dirs = [
        Path(item["absolute_path"]).resolve().parent
        for item in packages
        if item.get("absolute_path")
    ]

    if not package_dirs:
        raise ValueError(
            "No package.json absolute paths were found in project_report.json"
        )

    return Path(os.path.commonpath([str(p) for p in package_dirs]))


def extract_imports(source):
    imports = []

    for match in IMPORT_PATTERN.finditer(source):
        specifier = match.group(1) or match.group(2)

        if specifier and specifier not in imports:
            imports.append(specifier)

    return imports


def resolve_local_import(source_file, specifier):
    base = (source_file.parent / specifier).resolve()

    # Check the exact path first.
    candidates = [base]

    # Check common extensions for extensionless imports.
    if not base.suffix:
        candidates.extend(
            Path(str(base) + ext) for ext in EXTENSIONS
        )

    # Check directory index files.
    if not base.suffix or base.is_dir():
        candidates.extend(
            base / ("index" + ext) for ext in EXTENSIONS
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def load_manifests(project_root):
    manifests = []

    for current, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        if "package.json" not in files:
            continue

        manifest_path = Path(current) / "package.json"

        try:
            data = read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue

        manifests.append({
            "path": manifest_path.resolve(),
            "data": data
        })

    return manifests


def declared_packages(source_file, manifests):
    """Use manifests that are ancestors of this source file."""
    declared = set()

    for manifest in manifests:
        manifest_dir = manifest["path"].parent

        try:
            source_file.relative_to(manifest_dir)
        except ValueError:
            continue

        data = manifest["data"]

        for section in (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies"
        ):
            declared.update(data.get(section, {}).keys())

    return declared


def package_name(specifier):
    if specifier.startswith("@"):
        parts = specifier.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else specifier

    return specifier.split("/")[0]


def analyze():
    if not PROJECT_REPORT.is_file():
        raise FileNotFoundError(
            f"Missing project report: {PROJECT_REPORT}"
        )

    if not SOURCE_REPORT.is_file():
        raise FileNotFoundError(
            f"Missing source analysis. Run source_analyzer.py first: "
            f"{SOURCE_REPORT}"
        )

    project_report = read_json(PROJECT_REPORT)
    source_reports = read_json(SOURCE_REPORT)

    project_root = find_project_root(project_report)
    manifests = load_manifests(project_root)

    findings = []
    checked_files = 0

    for report in source_reports:
        reported_path = Path(report["file"])

        if not reported_path.is_absolute():
            reported_path = project_root / reported_path

        source_file = reported_path.resolve()

        try:
            source_file.relative_to(project_root)
        except ValueError:
            findings.append({
                "type": "source_path_outside_project",
                "file": str(source_file),
                "severity": "info",
                "message": "Source report path is outside the detected project root."
            })
            continue

        if not source_file.is_file():
            findings.append({
                "type": "source_file_missing",
                "file": str(source_file),
                "severity": "high",
                "message": "File listed in source analysis no longer exists."
            })
            continue

        try:
            source = source_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        checked_files += 1

        for specifier in extract_imports(source):
            # Relative imports refer to project files.
            if specifier.startswith("."):
                target = resolve_local_import(source_file, specifier)

                if target is None:
                    findings.append({
                        "type": "unresolved_local_import",
                        "file": str(source_file),
                        "import": specifier,
                        "severity": "high",
                        "message": (
                            "Could not resolve this relative import using "
                            "the common extensions and index-file conventions."
                        )
                    })

                continue

            # These require custom alias or import-map configuration.
            if specifier.startswith("@/") or specifier.startswith("#"):
                findings.append({
                    "type": "unverified_import_alias",
                    "file": str(source_file),
                    "import": specifier,
                    "severity": "info",
                    "message": "Import alias needs project-specific resolution rules."
                })
                continue

            # Ignore Node.js built-ins.
            if (
                specifier.startswith("node:")
                or package_name(specifier) in NODE_BUILTINS
            ):
                continue

            name = package_name(specifier)
            declared = declared_packages(source_file, manifests)

            if name not in declared:
                findings.append({
                    "type": "package_not_declared",
                    "file": str(source_file),
                    "import": specifier,
                    "package": name,
                    "severity": "medium",
                    "message": (
                        "Package was not found in the applicable package.json "
                        "dependency sections."
                    )
                })

    result = {
        "project_name": project_report.get("project_name"),
        "project_root": str(project_root),
        "source_files_checked": checked_files,
        "package_manifests_found": len(manifests),
        "findings_count": len(findings),
        "findings": findings,
        "limitations": [
            "Only common JavaScript import forms are extracted.",
            "TypeScript and custom bundler aliases are not fully resolved.",
            "Monorepo and workspace dependency rules may need extra handling.",
            "A reported unresolved import requires validation before declaring a confirmed failure."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_REPORT.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)

    print(f"Project: {result['project_name']}")
    print(f"Project root: {project_root}")
    print(f"Source files checked: {checked_files}")
    print(f"Package manifests found: {len(manifests)}")
    print(f"Import findings: {len(findings)}")
    print(f"Saved: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        analyze()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(f"Import analysis failed: {error}")