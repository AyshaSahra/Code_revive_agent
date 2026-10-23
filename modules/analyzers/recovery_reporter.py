import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).resolve().parents[2]))
from modules.utils import load_json, OUTPUT_DIR

# Input report paths
EVIDENCE_STORE = OUTPUT_DIR / "evidence_store.json"
PROJECT_REPORT = OUTPUT_DIR / "project_report.json"
PROJECT_STRUCTURE = OUTPUT_DIR / "project_structure.json"
TECH_STACK = OUTPUT_DIR / "tech_stack_used.json"
DATABASE_ANALYSIS = OUTPUT_DIR / "database_analysis.json"

OUTPUT_REPORT = OUTPUT_DIR / "recovery_report.json"

def safe_load(path, default=None):
    if default is None:
        default = {}
    try:
        if path.is_file():
            data = load_json(path)
            # Ensure we don't return None if the JSON file strictly contains `null`
            if data is not None:
                return data
    except Exception:
        pass
    return default

def categorize_certainty(record):
    """Categorize a finding as confirmed, potential, or unverified based on keywords and severity."""
    rule = str(record.get("rule") or "").lower()
    message = str(record.get("message") or "").lower()
    severity = str(record.get("severity") or "").lower()

    if "potential" in rule or "potential" in message or "heuristic" in message:
        return "potential"
    if "alias" in rule or "unverified" in message or severity == "info":
        return "unverified"
    
    # Syntax errors, crashes, missing files, and hardcoded secrets are typically confirmed
    return "confirmed"

def generate_recovery_plan(findings):
    """Draft prioritized recovery steps based on aggregated evidence."""
    plan = []
    seen_rules = set()

    for item in findings:
        # Force string casting to prevent NoneType iterable crashes
        rule = str(item.get("rule") or "unknown_issue")
        severity = str(item.get("severity") or "info").lower()
        file_path = str(item.get("affected_file") or "unknown_file")
        
        if rule in seen_rules:
            continue

        if severity in ["critical", "high"]:
            if "hardcoded" in rule.lower():
                plan.append(f"CRITICAL: Move hardcoded secrets/credentials in {file_path} to environment variables.")
            elif "syntax" in rule.lower() or "failure" in rule.lower() or "invalid" in rule.lower():
                plan.append(f"HIGH PRIORITY: Fix syntax or parsing errors breaking compilation in {file_path}.")
            elif "swallowed" in rule.lower() or "catch" in rule.lower():
                plan.append(f"HIGH PRIORITY: Implement proper error handling for empty catch blocks to reveal hidden runtime errors.")
            else:
                plan.append(f"HIGH PRIORITY: Investigate and resolve '{rule}' in {file_path}.")
            seen_rules.add(rule)

    for item in findings:
        rule = str(item.get("rule") or "unknown_issue")
        severity = str(item.get("severity") or "info").lower()
        file_path = str(item.get("affected_file") or "unknown_file")
        
        if rule in seen_rules:
            continue
            
        if severity == "medium":
            plan.append(f"MEDIUM PRIORITY: Review {file_path} for '{rule}'.")
            seen_rules.add(rule)

    if not plan:
        plan.append("No critical or high-priority issues detected requiring immediate recovery steps.")
        
    return plan

def generate_report():
    evidence_data = safe_load(EVIDENCE_STORE)
    project_data = safe_load(PROJECT_REPORT)
    structure_data = safe_load(PROJECT_STRUCTURE)
    tech_data = safe_load(TECH_STACK, default=[])
    db_data = safe_load(DATABASE_ANALYSIS)

    # 1. Aggregate Overview
    project_name = project_data.get("project_name", "unknown")
    
    technologies = []
    for pkg in tech_data:
        for cat, techs in pkg.get("technologies_detected_from_package_dependencies", {}).items():
            technologies.extend(techs)
    technologies = sorted(list(set(technologies)))

    architecture = structure_data.get("architecture", {}).get("type", "unverified")
    databases = db_data.get("technologies", [])

    # 2. Process Findings
    raw_evidence = evidence_data.get("evidence", [])
    processed_findings = []
    
    for record in raw_evidence:
        severity = str(record.get("severity") or "info").lower()
        
        # Standardize priority sorting
        priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
        sort_weight = priority_map.get(severity, 6)

        processed_findings.append({
            "priority": "Critical/High" if sort_weight <= 2 else ("Medium" if sort_weight == 3 else "Low/Info"),
            "severity": severity,
            "status_category": categorize_certainty(record),
            "rule": str(record.get("rule") or "unknown"),
            "affected_file": str(record.get("file") or "unknown"),
            "message": str(record.get("message") or ""),
            "evidence_snippet": str(record.get("evidence") or "").strip()[:200],
            "_weight": sort_weight
        })

    # Sort by severity weight
    processed_findings.sort(key=lambda x: x["_weight"])
    
    # Clean up sorting key
    for pf in processed_findings:
        del pf["_weight"]

    # 3. Compile final report
    report = {
        "project_name": project_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_overview": {
            "technologies_detected": technologies,
            "architecture_identified": architecture,
            "databases_identified": databases
        },
        "recovery_plan": generate_recovery_plan(processed_findings),
        "total_findings": len(processed_findings),
        "findings": processed_findings,
        "limitations": [
            "This recovery report is derived purely from static analysis evidence.",
            "Dynamic runtime errors, active network failures, and live database state are not represented.",
            "Potential issues require manual developer verification to confirm they impact production."
        ]
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    print("\nRecovery report generated successfully.")
    print(f"Total findings aggregated: {len(processed_findings)}")
    print(f"Report saved to: {OUTPUT_REPORT}")

if __name__ == "__main__":
    try:
        generate_report()
    except Exception as error:
        print(f"Recovery reporter failed: {error}")
        sys.exit(1)