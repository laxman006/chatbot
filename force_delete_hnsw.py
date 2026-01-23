"""
Force delete HNSW index files by identifying and optionally closing locking processes
"""
import os
import sys
import time
import subprocess
from pathlib import Path

def find_locking_process(file_path):
    """Find which process is locking a file (Windows)"""
    try:
        # Use handle.exe if available, or PowerShell
        cmd = f'powershell -Command "Get-Process | Where-Object {{$_.Path}} | ForEach-Object {{ try {{ [System.IO.File]::Open(\'{file_path}\', \'Open\', \'ReadWrite\', \'None\') | Out-Null; Write-Host \'$($_.ProcessName) (PID: $($_.Id))\' }} catch {{}} }}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error checking: {e}"

def main():
    jira_db_path = Path("data/jira_chroma_db")
    hnsw_index_dir = jira_db_path / "a1ae561b-dc51-4881-b3ba-e06b2f6dd9df"
    
    if not hnsw_index_dir.exists():
        print("✓ HNSW index directory doesn't exist - already deleted!")
        return
    
    print("=" * 70)
    print("FORCE DELETE HNSW INDEX FILES")
    print("=" * 70)
    print(f"\nDirectory: {hnsw_index_dir}")
    print("\nFiles to delete:")
    total_size = 0
    for file in hnsw_index_dir.iterdir():
        if file.is_file():
            size = file.stat().st_size
            total_size += size
            print(f"  • {file.name}: {size / (1024*1024):.2f} MB")
    print(f"\nTotal size: {total_size / (1024*1024):.2f} MB")
    
    # Check for locking processes
    print("\n" + "=" * 70)
    print("CHECKING FOR LOCKING PROCESSES...")
    print("=" * 70)
    
    sample_file = hnsw_index_dir / "data_level0.bin"
    if sample_file.exists():
        locking_info = find_locking_process(str(sample_file.absolute()))
        if locking_info:
            print(f"\n[WARNING] Files may be locked by: {locking_info}")
        else:
            print("\n[WARNING] Could not determine locking process")
    
    print("\n" + "=" * 70)
    print("SOLUTION OPTIONS:")
    print("=" * 70)
    print("\nOption 1: Close Python processes/server")
    print("  - Stop any running Python server (Ctrl+C in terminal)")
    print("  - Close any Python scripts that might be using the database")
    print("  - Then run: python delete_hnsw_index.py")
    
    print("\nOption 2: Delete entire database directory (RECOMMENDED)")
    print("  - This will delete everything including SQLite database")
    print("  - You'll need to rebuild anyway since index is corrupted")
    print("  - After closing Python processes, run:")
    print(f'    Remove-Item -Path "{jira_db_path}" -Recurse -Force')
    
    print("\nOption 3: Manual deletion")
    print("  - Close Cursor/VS Code")
    print("  - Close all Python processes")
    print("  - Manually delete the folder in File Explorer")
    print(f"  - Path: {hnsw_index_dir.absolute()}")
    
    print("\n" + "=" * 70)
    
    # Try deletion anyway
    print("\nAttempting deletion...")
    try:
        import shutil
        shutil.rmtree(hnsw_index_dir)
        print("✓ Successfully deleted!")
    except PermissionError:
        print("✗ Files are locked. Please use one of the options above.")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()
