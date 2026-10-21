
import json
import re
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
OUTPUT_REPORT = OUTPUT_DIR / "static_analysis.json"

IGNORED_DIRS = {
    "node_modules", ".git", "build", "dist",
    ".next", "coverage", "__pycache__"
}

SOURCE_EXTENSIONS = {".js", ".jsx"}


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def find_project_root(report):
    manifests = report.get("package_json_analysis", [])

    manifest_dirs = [
        Path(item["absolute_path"]).resolve().parent
        for item in manifests
        if item.get("absolute_path")
    ]

    if not manifest_dirs:
        raise ValueError(
            "No absolute package.json paths found in project_report.json"
        )

    # Works for a project with client/ and server/ manifests.
    return Path(
        __import__("os").path.commonpath(
            [str(path) for path in manifest_dirs]
        ))


def discover_source_files(project_root):
    files = []

    for current_root, dirs, filenames in __import__("os").walk(project_root):
        dirs[:] = [
            name for name in dirs
            if name not in IGNORED_DIRS
        ]

        for filename in filenames:
            path = Path(current_root) / filename

            if path.suffix.lower() in SOURCE_EXTENSIONS:
                files.append(path)

    return sorted(files)


def add_finding(findings, file_path, line, rule, severity, message, evidence):
    findings.append({
        "file": str(file_path),
        "line": line,
        "rule": rule,
        "severity": severity,
        "message": message,
        "evidence": evidence.strip()[:250]
    })


def analyze_file(file_path, project_root, findings):
    try:
        source = file_path.read_text(
            encoding="utf-8-sig",
            errors="replace"
        )
    except OSError as error:
        return False, str(error)

    relative_path = str(file_path.relative_to(project_root))
    lines = source.splitlines()

    # Basic static checks. These are heuristic findings, not guarantees.
    checks = [
        (
            "debugger_statement",
            re.compile(r"\bdebugger\s*;?"),
            "low",
            "Debugger statement found; it may interrupt execution."
        ),
        (
            "eval_usage",
            re.compile(r"\beval\s*\("),
            "medium",
            "eval() found; review for security and maintainability risks."
        ),
        (
            "console_log",
            re.compile(r"\bconsole\.log\s*\("),
            "info",
            "console.log() found; verify whether this debug output is intentional."
        ),
        (
            "todo_marker",
            re.compile(r"\b(?:TODO|FIXME|HACK)\b", re.IGNORECASE),
            "info",
            "TODO/FIXME/HACK marker found; review whether work remains."
        ),
    ]

    for line_number, line_text in enumerate(lines, start=1):
        for rule, pattern, severity, message in checks:
            if pattern.search(line_text):
                add_finding(
                    findings,
                    relative_path,
                    line_number,
                    rule,
                    severity,
                    message,
                    line_text
                )

    # Heuristic: an empty catch block can hide errors.
    empty_catch = re.compile(
        r"catch\s*(?:\([^)]*\))?\s*\{\s*\}",
        re.MULTILINE
    )

    for match in empty_catch.finditer(source):
        line_number = source.count("\n", 0, match.start()) + 1
        add_finding(
            findings,
            relative_path,
            line_number,
            "empty_catch_block",
            "medium",
            "Empty catch block may silently hide an error.",
            match.group(0)
        )

    # Optional syntax parsing using Tree-sitter.
    try:
        import tree_sitter_javascript
        from tree_sitter import Language, Parser

        language = Language(tree_sitter_javascript.language())
        parser = Parser(language)
        tree = parser.parse(source.encode("utf-8"))

        def inspect_node(node):
            if node.type == "ERROR" or node.is_missing:
                start_line = node.start_point[0] + 1
                add_finding(
                    findings,
                    relative_path,
                    start_line,
                    "parser_syntax_error",
                    "high",
                    "Tree-sitter reported a syntax error or missing syntax node.",
                    source.splitlines()[start_line - 1]
                    if start_line <= len(lines) else node.type
                )

            for child in node.children:
                inspect_node(child)

        inspect_node(tree.root_node)

    except ImportError:
        # Regex checks still work when Tree-sitter is not installed.
        pass
    except Exception as error:
        add_finding(
            findings,
            relative_path,
            1,
            "parser_failure",
            "info",
            f"Tree-sitter could not analyze this file: {error}",
            ""
        )

    return True, None


def main():
    if not PROJECT_REPORT.exists():
        raise FileNotFoundError(
            f"Missing project report: {PROJECT_REPORT}"
        )

    report = load_json(PROJECT_REPORT)
    project_root = find_project_root(report)

    if not project_root.is_dir():
        raise NotADirectoryError(
            f"Target project directory not found: {project_root}"
        )

    source_files = discover_source_files(project_root)
    findings = []
    checked_files = 0
    read_errors = []

    for file_path in source_files:
        success, error = analyze_file(
            file_path, project_root, findings
        )

        if success:
            checked_files += 1
        else:
            read_errors.append({
                "file": str(file_path),
                "error": error
            })

    result = {
        "project_name": report.get("project_name", project_root.name),
        "project_root": str(project_root),
        "analysis_type": "static_analysis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_discovered": len(source_files),
        "files_checked": checked_files,
        "files_unreadable": len(read_errors),
        "findings_count": len(findings),
        "findings_by_severity": {
            severity: sum(
                1 for item in findings
                if item["severity"] == severity
            )
            for severity in ["high", "medium", "low", "info"]
        },
        "findings": findings,
        "read_errors": read_errors,
        "limitations": [
            "Heuristic patterns can produce false positives.",
            "Only JavaScript and JSX files are scanned.",
            "Syntax parsing is available only when Tree-sitter dependencies are installed.",
            "This does not prove runtime correctness."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )

    print("Static analysis completed.")
    print(f"Project: {project_root}")
    print(f"Files discovered: {len(source_files)}")
    print(f"Files checked: {checked_files}")
    print(f"Findings: {len(findings)}")
    print(f"Report saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Static analysis failed: {error}")