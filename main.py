import sys
import subprocess
from pathlib import Path

def print_header(title):
    print("\n" + "="*60)
    print(f"🚀 {title}")
    print("="*60)

def run_stage(module_name, args=None):
    """Executes a module via subprocess to guarantee isolation and preserve original behavior."""
    print(f"\n---> Starting Stage: {module_name}")
    
    command = [sys.executable, "-m", module_name]
    if args:
        command.extend(args)

    try:
        # Run the process and pipe output directly to the console so original prints are preserved
        subprocess.run(command, check=True)
        print(f"---> ✅ Stage '{module_name}' completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n---> ❌ ERROR: Stage '{module_name}' failed with exit code {e.returncode}.")
        return False
    except Exception as e:
        print(f"\n---> ❌ FATAL ERROR: Could not execute '{module_name}'. Details: {e}")
        return False

def main():
    print_header("Code Revive Agent - Analysis Pipeline")

    # 1. Handle target directory input
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        target_dir = input("Enter the path of the directory to analyze: ").strip()

    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        print(f"❌ Error: The provided path '{target_path}' is not a valid directory.")
        sys.exit(1)

    print(f"Target Directory: {target_path}")

    # 2. Define the execution plan (Dependency-aware order)
    pipeline = [
        ("modules.scanner.scan_files", [str(target_path)]),
        ("modules.scanner.structure_analyzer", []),
        ("modules.scanner.techstack_detection", []),
        ("modules.analyzers.source_analyzer", []),
        ("modules.analyzers.import_analyzer", []),
        ("modules.analyzers.static_analyzer", []),
        ("modules.analyzers.dependency_analyzer", []),
        ("modules.analyzers.database_analyzer", []),
        ("modules.analyzers.build_analyzer", []),
        ("modules.analyzers.runtime_analyzer", []),
        ("modules.analyzers.evidence_store", []),
        ("modules.analyzers.recovery_reporter", [])
    ]

    # 3. Execute the pipeline with fault tolerance
    failed_modules = []

    for module, args in pipeline:
        success = run_stage(module, args)
        if not success:
            print(f"---> ⚠️ Skipping to the next stage...")
            failed_modules.append(module)

    # 4. Final Output Summary
    if failed_modules:
        print_header("Analysis Pipeline Completed with Errors ⚠️")
        print("The following modules encountered errors:")
        for fm in failed_modules:
            print(f"  - ❌ {fm}")
        print("\nHowever, the pipeline successfully continued and generated partial reports.")
    else:
        print_header("Analysis Pipeline Completed Successfully! 🎉")
        
    print(f"All available reports have been saved to: {Path('output').resolve()}")

if __name__ == "__main__":
    main()