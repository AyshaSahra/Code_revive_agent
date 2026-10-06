import os

# Folders to completely skip (won't even walk into them)
EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.vite', '.vscode', 'venv'}

# Specific file names to skip
EXCLUDE_FILES = {'.DS_Store', 'Thumbs.db'}

# File extensions to skip
EXCLUDE_EXTENSIONS = {'.sample', '.log', '.tmp'}

path = input("Enter the path of the directory to scan: ")

if os.path.isdir(path):
    print(f"\nFiles in '{path}' (including subfolders):")

    for root, dirs, files in os.walk(path):
        # Modify dirs in-place to prevent os.walk from descending into excluded folders
        dirs[:] = [d for d in dirs if d not in   EXCLUDE_DIRS]

        for filename in files:
            if filename in EXCLUDE_FILES:
                continue
            if os.path.splitext(filename)[1].lower() in EXCLUDE_EXTENSIONS:
                continue
            print(filename)

else:
    print("Invalid directory path.")