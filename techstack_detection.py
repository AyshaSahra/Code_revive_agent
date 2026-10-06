import os
import json


def load_technology_map():
    """Load technology_map.json from the config folder."""

    current_dir = os.path.dirname(os.path.abspath(__file__))
    tech_map_path = os.path.join(
        current_dir,
        "config",
        "technology_map.json"
    )

    if not os.path.isfile(tech_map_path):
        raise FileNotFoundError(
            f"Missing technology_map.json at {tech_map_path}. "
            "Please create the file with dependency-category mappings."
        )

    try:
        with open(tech_map_path, "r") as f:
            technology_map = json.load(f)

    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in technology_map.json: {e}"
        )

    return technology_map


def find_package_json(project_report_path):
    """Read project_report.json and locate package.json paths with absolute paths."""

    with open(project_report_path, "r") as f:
        report = json.load(f)

    package_json_analysis = report.get("package_json_analysis", [])
    if not package_json_analysis:
        raise FileNotFoundError("No package.json analysis found in project_report.json")

    # Collect all absolute paths
    package_json_paths = [p["absolute_path"] for p in package_json_analysis if "absolute_path" in p]

    if not package_json_paths:
        raise FileNotFoundError("No absolute paths found in project_report.json")

    return package_json_paths



def detect_tech_stack(dependencies):
    """Match dependency names against technology_map."""

    technology_map = load_technology_map()

    detected = {}

    for dep_name in dependencies:

        base_name = dep_name.lower()

        for tech, category in technology_map.items():

            if tech.lower() in base_name:
                detected[dep_name] = category

    return detected


def build_tech_stack_report(package_json_full_path):

    with open(package_json_full_path, "r") as f:
        package_data = json.load(f)

    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("devDependencies", {})
    scripts = package_data.get("scripts", {})

    project_name = package_data.get("name", "Unknown")
    project_version = package_data.get("version", "Unknown")

    all_deps = {
        **dependencies,
        **dev_dependencies
    }

    identified_tech = detect_tech_stack(all_deps)

    report = {
        "project_name": project_name,
        "project_version": project_version,
        "dependencies": dependencies,
        "dev_dependencies": dev_dependencies,
        "scripts": scripts,
        "identified_technologies": identified_tech
    }

    return report


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_report_path = os.path.join(current_dir, "config", "project_report.json")

    if not os.path.isfile(project_report_path):
        print(f"project_report.json not found at: {project_report_path}")
        return

    try:
        package_json_paths = find_package_json(project_report_path)
    except FileNotFoundError as e:
        print(e)
        return

    all_reports = []
    for full_package_json_path in package_json_paths:
        if not os.path.isfile(full_package_json_path):
            print(f"Could not find package.json at: {full_package_json_path}")
            continue

        tech_stack_report = build_tech_stack_report(full_package_json_path)
        all_reports.append(tech_stack_report)

    # Save combined report
    output_file = os.path.join(current_dir, "config", "tech_stack_used.json")
    with open(output_file, "w") as f:
        json.dump(all_reports, f, indent=4)

    print(f"\nTech stack report saved to: {output_file}")



if __name__ == "__main__":
    main()