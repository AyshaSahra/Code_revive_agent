import os
import json
from tree_sitter import Language, Parser
import tree_sitter_javascript

JS_LANGUAGE = Language(tree_sitter_javascript.language())
parser = Parser(JS_LANGUAGE)


def walk_project_files(project_dir):
    """Collect project JavaScript files while skipping generated/dependency folders."""

    js_files = []

    ignored_dirs = {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        "__pycache__"
    }

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

    output_folder = "output"

    report_file = os.path.join(
        output_folder,
        "project_report.json"
    )

    with open(report_file, "r", encoding="utf8") as f:
        report_data = json.load(f)

    # Get all detected package.json paths
    package_paths = [
        item["absolute_path"]
        for item in report_data["package_json_analysis"]
    ]

    # Get directories containing package.json
    package_directories = [
        os.path.dirname(path)
        for path in package_paths
    ]

    # Find common project root
    project_path = os.path.commonpath(
        package_directories
    )

    print("Detected project root:")
    print(project_path)

    output_file = os.path.join(
        output_folder,
        "source_analysis.json"
    )

    analyze_project(
        project_path,
        output_file
    )