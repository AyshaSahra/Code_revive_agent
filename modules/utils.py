import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_DIR = BASE_DIR / "config"

def load_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)

def load_config(filename):
    return load_json(CONFIG_DIR / filename)

def find_project_root(report):
    """Find the common parent of all reported package.json directories."""
    packages = report.get("package_json_analysis", [])
    package_dirs = [
        Path(item["absolute_path"]).resolve().parent
        for item in packages if item.get("absolute_path")
    ]
    if not package_dirs:
        raise ValueError("No package.json absolute paths found.")
    return Path(os.path.commonpath([str(p) for p in package_dirs]))