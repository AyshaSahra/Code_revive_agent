import os
import json
from collections import Counter

def load_config():
    """Load scanner configuration from scanner_config.json."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir,"config", "scanner_config.json")

    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"Missing scanner_config.json at {config_path}. "
            "Please create the file with scanner rules."
        )

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in scanner_config.json: {e}")

    # Convert lists to sets where appropriate
    config["exclude_directories"] = set(config.get("exclude_directories", []))
    config["exclude_files"] = set(config.get("exclude_files", []))
    config["exclude_extensions"] = set(config.get("exclude_extensions", []))
    config["important_files"] = set(config.get("important_files", []))

    return config


def scan_directory(path, config):
    """Walk the directory and collect file info, skipping excluded dirs/files."""
    all_files = []
    extension_counter = Counter()
    important_files_found = []

    for root, dirs, files in os.walk(path):
        # Prevent walking into excluded folders
        dirs[:] = [d for d in dirs if d not in config["exclude_directories"]]

        for filename in files:
            if filename in config["exclude_files"]:
                continue

            ext = os.path.splitext(filename)[1]
            if ext in config["exclude_extensions"]:
                continue

            all_files.append(filename)
            extension_counter[ext] += 1

            if filename in config["important_files"]:
                rel_path = os.path.relpath(os.path.join(root, filename), path)
                important_files_found.append(rel_path)

    return all_files, extension_counter, important_files_found


def detect_languages(extension_counter, config):
    """Convert extension counts into a readable list of languages used."""
    languages = set()
    for ext in extension_counter:
        if ext in config["extension_language_map"]:
            languages.add(config["extension_language_map"][ext])
    return sorted(languages) if languages else ["Unknown"]


def find_package_json_files(path, config):
    """Find all package.json files in the project, excluding ignored directories."""
    package_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in config["exclude_directories"]]
        for filename in files:
            if filename == "package.json":
                rel_path = os.path.relpath(os.path.join(root, filename), path)
                package_files.append(rel_path)
    return package_files


def load_technology_map():
    """Load technology_map.json from the config folder."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tech_map_path = os.path.join(current_dir, "config", "technology_map.json")

    if not os.path.isfile(tech_map_path):
        raise FileNotFoundError(
            f"Missing technology_map.json at {tech_map_path}. "
            "Please create the file with dependency-category mappings."
        )

    try:
        with open(tech_map_path, "r") as f:
            technology_map = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in technology_map.json: {e}")

    return technology_map


def detect_technologies(dependencies, dev_dependencies, scripts, technology_map):
    """Detect technologies based on dependencies and scripts using external map."""
    detected = {}

    all_deps = list(dependencies.keys()) + list(dev_dependencies.keys())

    for dep in all_deps:
        base_name = dep.lower()
        for tech, category in technology_map.items():
            if tech.lower() in base_name:
                detected[dep] = category

    for script_name, script_cmd in scripts.items():
        for tech, category in technology_map.items():
            if tech.lower() in script_cmd.lower():
                detected[f"script:{script_name}"] = category

    return detected


def analyze_package_json(path, rel_path, technology_map):
    """Read and analyze a package.json file."""
    try:
        with open(path, "r") as f:
            package_data = json.load(f)
    except json.JSONDecodeError as e:
        return {"file_path": rel_path, "error": f"Invalid JSON: {e}"}
    except Exception as e:
        return {"file_path": rel_path, "error": str(e)}

    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("devDependencies", {})
    scripts = package_data.get("scripts", {})

    technologies = detect_technologies(dependencies, dev_dependencies, scripts, technology_map)

    return {
        "file_path": rel_path,
        "package_name": package_data.get("name"),
        "absolute_path": path,
        "version": package_data.get("version"),
        "description": package_data.get("description"),
        "dependencies": dependencies,
        "dev_dependencies": dev_dependencies,
        "scripts": scripts,
        "technologies_detected": technologies
    }



def build_report(path, config):
    project_name = os.path.basename(os.path.normpath(path))
    all_files, extension_counter, important_files = scan_directory(path, config)

    # Load technology map once here
    technology_map = load_technology_map()

    package_files = find_package_json_files(path, config)
    package_analysis = []
    for rel_path in package_files:
        full_path = os.path.join(path, rel_path)
        package_analysis.append(analyze_package_json(full_path, rel_path, technology_map))

    report = {
        "project_name": project_name,
        "total_files": len(all_files),
        "file_types_detected": detect_languages(extension_counter, config),
        "important_files": important_files,
        "package_json_analysis": package_analysis
    }
    return report



def main():
    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return

    path = input("Enter the path of the directory to scan: ")

    if not os.path.isdir(path):
        print("Invalid directory path.")
        return

    report = build_report(path, config)

    # Save report inside the config folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(
        current_dir,
        "config",
        "project_report.json"
    )

    with open(output_file, "w") as f:
        json.dump(report, f, indent=4)

    print(f"\nReport saved to '{output_file}'")


if __name__ == "__main__":
    main()
