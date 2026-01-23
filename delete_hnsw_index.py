"""
Script to delete corrupted HNSW index files
Handles file locks by retrying with delays
"""
import os
import shutil
import time
from pathlib import Path

jira_db_path = Path("data/jira_chroma_db")
hnsw_index_dir = jira_db_path / "a1ae561b-dc51-4881-b3ba-e06b2f6dd9df"

if not hnsw_index_dir.exists():
    print("HNSW index directory not found - already deleted or doesn't exist")
    exit(0)

print(f"Attempting to delete HNSW index directory: {hnsw_index_dir}")
print("Files to delete:")
for file in hnsw_index_dir.iterdir():
    if file.is_file():
        size = file.stat().st_size / (1024 * 1024)
        print(f"  • {file.name}: {size:.2f} MB")

# Try multiple times with delays
max_retries = 5
retry_delay = 2

for attempt in range(1, max_retries + 1):
    try:
        print(f"\nAttempt {attempt}/{max_retries}...")
        shutil.rmtree(hnsw_index_dir)
        print("✓ HNSW index files deleted successfully!")
        break
    except PermissionError as e:
        if attempt < max_retries:
            print(f"⚠ Files locked, waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
        else:
            print(f"✗ Failed to delete after {max_retries} attempts")
            print(f"Error: {e}")
            print("\nPlease close any applications using these files (Python, ChromaDB, etc.)")
            print("Then manually delete the directory:")
            print(f"  {hnsw_index_dir}")
            exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        exit(1)

# Verify deletion
if not hnsw_index_dir.exists():
    print("\n✓ Verification: Directory successfully deleted")
    print("\nRemaining files in jira_chroma_db:")
    if jira_db_path.exists():
        for item in jira_db_path.iterdir():
            if item.is_file():
                size = item.stat().st_size / (1024 * 1024)
                print(f"  • {item.name}: {size:.2f} MB")
            elif item.is_dir():
                print(f"  • {item.name}/ (directory)")
    else:
        print("  (directory doesn't exist)")
else:
    print("\n⚠ Warning: Directory still exists after deletion attempt")
