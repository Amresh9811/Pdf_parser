"""
Script to create the required project structure.
"""
import os
from pathlib import Path

# Define structure
structure = {
    'config': ['__init__.py'],
    'pipeline': ['__init__.py'],
    'pipeline/api': ['__init__.py'],
    'pipeline/extractors': ['__init__.py'],
    'pipeline/services': ['__init__.py'],
    'pipeline/tasks': ['__init__.py'],
    'pipeline/flows': ['__init__.py'],
    'data/chroma': [],
    'data/documents': [],
    'data/processed': [],
    'logs': []
}

# Create directories and files
base_dir = Path(__file__).parent

for directory, files in structure.items():
    dir_path = base_dir / directory
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"Created: {dir_path}")
    
    for file in files:
        file_path = dir_path / file
        file_path.touch(exist_ok=True)
        print(f"Created: {file_path}")

print("\n✅ Project structure created successfully!")
print("\nNow move your files to the correct locations as specified.")