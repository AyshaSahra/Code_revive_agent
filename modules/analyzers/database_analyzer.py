import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, load_config, find_project_root, OUTPUT_DIR

PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
TECH_STACK_REPORT = OUTPUT_DIR / "tech_stack_used.json"
OUTPUT_REPORT = OUTPUT_DIR / "database_analysis.json"
CONFIG = load_config("scanner_config.json")

# Common DB driver and ORM packages
DB_INDICATORS = {"mongoose", "mongodb", "mysql", "mysql2", "pg", "sqlite3", "sequelize", "prisma", "typeorm"}

# Regex patterns for DB analysis
PATTERNS = {
    "connection": re.compile(r"(mongoose\.connect|new MongoClient|createConnection|new Pool|new Sequelize)\s*\(([^)]+)\)", re.IGNORECASE),
    "env_var": re.compile(r"process\.env\.([A-Z0-9_]+)"),
    "schema_model": re.compile(r"(new Schema|sequelize\.define|\.model)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    "crud_operation": re.compile(r"\.(find|findOne|insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|query|create|save|destroy)\s*\(", re.IGNORECASE),
    "uri_redaction": re.compile(r"(mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://([^:@]+):([^@]+)@"),
    
    # Strict Code-Level Error Detection Patterns
    "hardcoded_uri": re.compile(r"['\"](mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://", re.IGNORECASE),
    "empty_promise_catch": re.compile(r"\.catch\s*\(\s*(?:\([^)]*\)|[a-zA-Z0-9_]+)?\s*(?:=>)?\s*\{\s*\}\s*\)", re.IGNORECASE)
}

def redact_credentials(text):
    """Masks username:password inside connection URIs."""
    return PATTERNS["uri_redaction"].sub(r"\1://***:***@", text)

def discover_source_files(project_root):
    files = []
    source_exts = [ext for ext, lang in CONFIG["extension_language_map"].items() if "JavaScript" in lang or "TypeScript" in lang]
    
    for current_root, dirs, filenames in __import__("os").walk(project_root):
        dirs[:] = [name for name in dirs if name not in CONFIG["exclude_directories"]]
        for filename in filenames:
            path = Path(current_root) / filename
            if path.suffix.lower() in source_exts:
                files.append(path)
    return sorted(files)

def analyze_db_usage():
    if not PROJECT_REPORT.exists():
        raise FileNotFoundError(f"Missing report: {PROJECT_REPORT}")
    if not TECH_STACK_REPORT.exists():
        raise FileNotFoundError(f"Missing report: {TECH_STACK_REPORT}")

    report = load_json(PROJECT_REPORT)
    tech_stack = load_json(TECH_STACK_REPORT)
    project_root = find_project_root(report)

    # 1. Detect DB Technologies from dependencies
    detected_dbs = set()
    for package in tech_stack:
        deps = package.get("technologies_detected_from_package_dependencies", {})
        for category, techs in deps.items():
            for tech in techs:
                if tech.lower() in DB_INDICATORS:
                    detected_dbs.add(tech.lower())

    if not detected_dbs:
        return {
            "project_name": report.get("project_name", "unknown"),
            "status": "no_database_detected",
            "technologies": [],
            "message": "No recognized database drivers or ORMs found in dependencies."
        }

    # 2. Analyze Source Code for DB implementation & Errors
    source_files = discover_source_files(project_root)
    
    connections = []
    models = []
    operations = []
    findings = []

    for file_path in source_files:
        try:
            source = file_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue

        relative_path = str(file_path.relative_to(project_root))
        lines = source.splitlines()

        for line_number, line_text in enumerate(lines, start=1):
            
            # --- CONNECTION EXTRACTION ---
            for match in PATTERNS["connection"].finditer(line_text):
                safe_evidence = redact_credentials(line_text.strip())
                env_vars = PATTERNS["env_var"].findall(match.group(2))
                
                connections.append({
                    "file": relative_path,
                    "line": line_number,
                    "type": match.group(1),
                    "uses_env_vars": env_vars,
                    "evidence": safe_evidence
                })

            # --- MODEL EXTRACTION ---
            for match in PATTERNS["schema_model"].finditer(line_text):
                models.append({
                    "file": relative_path,
                    "line": line_number,
                    "entity_name": match.group(2),
                    "type": match.group(1)
                })

            # --- CRUD EXTRACTION & MISSING AWAIT CHECK ---
            for match in PATTERNS["crud_operation"].finditer(line_text):
                operations.append({
                    "file": relative_path,
                    "line": line_number,
                    "operation": match.group(1),
                    "evidence": line_text.strip()
                })
                
                # Rule: Unhandled database promise
                if "await" not in line_text and "return" not in line_text and ".then" not in line_text and ".catch" not in line_text:
                    findings.append({
                        "type": "unhandled_db_promise",
                        "file": relative_path,
                        "line": line_number,
                        "severity": "medium",
                        "message": f"Database operation '{match.group(1)}' appears to be missing an 'await' or return statement. This can cause silent failures or race conditions.",
                        "evidence": line_text.strip()
                    })

            # --- HARDCODED CREDENTIAL CHECK ---
            if PATTERNS["hardcoded_uri"].search(line_text):
                findings.append({
                    "type": "hardcoded_db_credentials",
                    "file": relative_path,
                    "line": line_number,
                    "severity": "critical",
                    "message": "A hardcoded database connection URI was detected. Use environment variables (process.env) instead.",
                    "evidence": redact_credentials(line_text.strip())
                })

            # --- EMPTY CATCH BLOCK CHECK ---
            if PATTERNS["empty_promise_catch"].search(line_text):
                findings.append({
                    "type": "swallowed_db_error",
                    "file": relative_path,
                    "line": line_number,
                    "severity": "high",
                    "message": "An empty .catch() block was detected. Database errors here will fail silently.",
                    "evidence": line_text.strip()
                })

    return {
        "project_name": report.get("project_name", "unknown"),
        "status": "database_analyzed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "technologies": list(detected_dbs),
        "metrics": {
            "connections_found": len(connections),
            "models_found": len(models),
            "operations_found": len(operations)
        },
        "connections": connections,
        "models": models,
        "operations_sample": operations[:20], 
        "findings": findings,
        "limitations": [
            "Analysis is purely static; no live database connections are made.",
            "Cannot verify if the connection URI is reachable or valid.",
            "Missing 'await' detection is heuristic and may produce false positives on complex promise chains."
        ]
    }

def main():
    try:
        result = analyze_db_usage()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        
        print("\nDatabase analysis completed.")
        print(f"Status: {result.get('status')}")
        print(f"Technologies: {', '.join(result.get('technologies', []))}")
        print(f"Findings: {len(result.get('findings', []))}")
        print(f"Report saved to: {OUTPUT_REPORT}")
    except Exception as error:
        print(f"Database analysis failed: {error}")

if __name__ == "__main__":
    main()