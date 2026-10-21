import os
import json
import sys
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_javascript

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, load_config, find_project_root, OUTPUT_DIR

CONFIG = load_config("scanner_config.json")

JS_LANGUAGE = Language(tree_sitter_javascript.language())
parser = Parser(JS_LANGUAGE)


def walk_project_files(project_dir):
    """Collect project JavaScript files while skipping generated/dependency folders."""

    js_files = []
    ignored_dirs = set(CONFIG["exclude_directories"])

    for root, dirs, files in os.walk(project_dir):

        # Prevent os.walk from entering ignored directories
        dirs[:] = [
            d for d in dirs
            if d not in ignored_dirs
        ]

        for f in files:
            if f.endswith(".js") or f.endswith(".jsx"):
                js_files.append(os.path.join(root, f))

    return js_files


def get_node_text(source_code, node):
    """Extract text for a given node."""
    return source_code[node.start_byte:node.end_byte].decode("utf8")


def traverse_tree(tree, source_code, file_path):
    """Traverse AST and extract structural info + syntax errors."""
    root = tree.root_node
    file_report = {
        "file": file_path,
        "imports": [],
        "exports": [],
        "functions": [],
        "classes": [],
        "variables": [],
        "calls": [],
        "syntax_errors": []
    }

    def walk(node):
        if node.type == "ERROR":
            file_report["syntax_errors"].append({
                "line": node.start_point[0] + 1,
                "column": node.start_point[1] + 1,
                "type": "syntax_error"
            })

        if node.type == "import_statement":
            file_report["imports"].append(get_node_text(source_code, node))

        if node.type.startswith("export"):
            file_report["exports"].append(get_node_text(source_code, node))

        if node.type in ["function_declaration", "method_definition"]:
            name_node = node.child_by_field_name("name")
            if name_node:
                file_report["functions"].append({
                    "name": get_node_text(source_code, name_node),
                    "line": name_node.start_point[0] + 1
                })

        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                file_report["classes"].append({
                    "name": get_node_text(source_code, name_node),
                    "line": name_node.start_point[0] + 1
                })

        if node.type == "variable_declarator":
            ident = node.child_by_field_name("name")
            if ident:
                file_report["variables"].append({
                    "name": get_node_text(source_code, ident),
                    "line": ident.start_point[0] + 1
                })

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                file_report["calls"].append({
                    "function": get_node_text(source_code, func),
                    "line": func.start_point[0] + 1
                })

        for child in node.children:
            walk(child)

    walk(root)
    return file_report


def analyze_project(project_dir, output_file):
    """Main analyzer function."""

    results = []

    js_files = walk_project_files(project_dir)

    print(f"Found {len(js_files)} JavaScript files")

    for index, file_path in enumerate(js_files, start=1):

        print(f"[{index}/{len(js_files)}] Analyzing: {file_path}")

        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = parser.parse(source_code)

        report = traverse_tree(
            tree,
            source_code,
            file_path
        )

        results.append(report)

    with open(output_file, "w", encoding="utf8") as out:
        json.dump(results, out, indent=2)

    print(f"Analysis complete. Results saved to {output_file}")


if __name__ == "__main__":

    report_file = OUTPUT_DIR / "project_report.json"

    if not report_file.exists():
        raise FileNotFoundError(f"Report not found: {report_file}")

    report_data = load_json(report_file)
    project_path = str(find_project_root(report_data))

    print("Detected project root:")
    print(project_path)

    output_file = OUTPUT_DIR / "source_analysis.json"

    analyze_project(
        project_path,
        str(output_file)
    )