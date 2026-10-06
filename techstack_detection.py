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


def load_project_report(project_report_path):
    """Read project_report.json to gather evidence already collected by the scanner."""
    if not os.path.isfile(project_report_path):
        raise FileNotFoundError(f"project_report.json not found at: {project_report_path}")

    try:
        with open(project_report_path, "r") as f:
            report = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in project_report.json: {e}")

    package_json_analysis = report.get("package_json_analysis", [])
    if not package_json_analysis:
        raise ValueError("No package_json_analysis data found in project_report.json")

    return package_json_analysis


def detect_tech_stack(dependencies, dev_dependencies, technology_map):
    """
    Match dependency names against the technology_map.
    Returns a dictionary grouped by category.
    """
    detected_grouped = {}
    
    all_deps = list(dependencies.keys()) + list(dev_dependencies.keys())

    # Helper function to add a tech to its category safely
    def add_to_category(category, item):
        if category not in detected_grouped:
            detected_grouped[category] = []
        if item not in detected_grouped[category]:
            detected_grouped[category].append(item)

    # Exact matching for dependencies (avoids substring false positives)
    for dep_name in all_deps:
        dep_lower = dep_name.lower()
        for tech, category in technology_map.items():
            if tech.lower() == dep_lower:
                add_to_category(category, dep_name)
                break # Move to next dependency once matched

    return detected_grouped


def build_tech_stack_report(package_data, technology_map):
    """Build the final tech stack report block for a single package file."""
    # Skip any package.json files that the scanner couldn't read properly
    if "error" in package_data:
        return None

    project_name = package_data.get("package_name", "Unknown")
    project_version = package_data.get("version", "Unknown")
    
    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("dev_dependencies", {})
    scripts = package_data.get("scripts", {})

    # We no longer pass scripts into the tech detection
    identified_tech = detect_tech_stack(dependencies, dev_dependencies, technology_map)

    report = {
        "project_name": project_name,
        "project_version": project_version,
        "technologies_detected_from_package_dependencies": identified_tech,
        "scripts_detected": scripts
    }

    return report


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_report_path = os.path.join(current_dir, "config", "project_report.json")

    try:
        package_json_analysis = load_project_report(project_report_path)
        technology_map = load_technology_map()
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return

    all_reports = []
    for package_data in package_json_analysis:
        tech_stack_report = build_tech_stack_report(package_data, technology_map)
        if tech_stack_report:
            all_reports.append(tech_stack_report)

    # Save combined technology report
    output_file = os.path.join(current_dir, "config", "tech_stack_used.json")
    with open(output_file, "w") as f:
        json.dump(all_reports, f, indent=4)

    print(f"\nTech stack report saved to: {output_file}")


if __name__ == "__main__":
    main()