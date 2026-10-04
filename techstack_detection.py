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
    """Read project_report.json and locate package.json paths."""

    with open(project_report_path, "r") as f:
        report = json.load(f)

    important_files = report.get("important_files", [])

    package_json_paths = [
        f for f in important_files
        if os.path.basename(f) == "package.json"
    ]

    if not package_json_paths:
        raise FileNotFoundError(
            "No package.json found in important_files list."
        )

    if len(package_json_paths) > 1:
        print("Multiple package.json files found:")

        for i, p in enumerate(package_json_paths, start=1):
            print(f"{i}. {p}")

        choice = input(
            f"Select which one to analyze (1-{len(package_json_paths)}): "
        )

        try:
            selected = package_json_paths[int(choice) - 1]

        except (ValueError, IndexError):
            print("Invalid choice, defaulting to the first one.")
            selected = package_json_paths[0]

    else:
        selected = package_json_paths[0]

    return selected


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

    # Location of this Python file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Automatically locate project_report.json
    project_report_path = os.path.join(
        current_dir,
        "config",
        "project_report.json"
    )

    if not os.path.isfile(project_report_path):
        print(
            f"project_report.json not found at: "
            f"{project_report_path}"
        )
        return

    try:
        relative_package_json_path = find_package_json(
            project_report_path
        )

    except FileNotFoundError as e:
        print(e)
        return

    # Ask for the original project that was scanned
    scanned_dir = input(
        "Enter the original scanned project directory path: "
    ).strip()

    if not os.path.isdir(scanned_dir):
        print("Invalid project directory path.")
        return

    # Convert the relative package.json path into a full path
    full_package_json_path = os.path.join(
        scanned_dir,
        relative_package_json_path
    )

    if not os.path.isfile(full_package_json_path):
        print(
            f"Could not find package.json at: "
            f"{full_package_json_path}"
        )
        return

    # Analyze package.json
    tech_stack_report = build_tech_stack_report(
        full_package_json_path
    )

    # Display report
    print("\nGenerated Tech Stack Report:")
    print(json.dumps(tech_stack_report, indent=4))

    # Save report inside config folder
    output_file = os.path.join(
        current_dir,
        "config",
        "tech_stack_used.json"
    )

    with open(output_file, "w") as f:
        json.dump(
            tech_stack_report,
            f,
            indent=4
        )

    print(
        f"\nTech stack report saved to: "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()