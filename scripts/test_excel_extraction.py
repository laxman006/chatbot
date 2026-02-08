import os
import sys
import pandas as pd
from typing import List, Dict

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.excel_processor import extract_excel_rows_as_chunks

def create_dummy_excel(filename: str):
    """Create a dummy Excel file for testing."""
    data = {
        "Feature": ["Test Feature 1", "Test Feature 2"],
        "Supported": ["Yes", "No"],
        "Description": ["Description 1", "Description 2"],
        "Notes": ["Limitation note 1", "Limitation note 2"]
    }
    df = pd.DataFrame(data)
    # Use a sheet name that implies a migration to test filtering fix
    file_path = os.path.abspath(filename)
    # Using 'Slack to Teams' related sheet name to test migration type assignment
    with pd.ExcelWriter(file_path) as writer:
        df.to_excel(writer, sheet_name="Slack to Teams", index=False)
    print(f"Created dummy Excel: {file_path}")
    return file_path

def test_extraction():
    excel_file = "test_data.xlsx"
    try:
        excel_path = create_dummy_excel(excel_file)
        
        print(f"Extracting chunks from: {excel_path}")
        chunks = extract_excel_rows_as_chunks(excel_path)
        
        print(f"Extracted {len(chunks)} chunks.")
        
        found_limitation_text = False
        found_migration_type = False
        found_limitation_field = False

        for i, chunk in enumerate(chunks):
            print(f"--- Chunk {i} ---")
            print(f"Type: {chunk.get('chunk_type')}")
            print(f"Content: {chunk.get('content')}")
            print(f"Migration Type: {chunk.get('migration_type')}")
            print(f"Limitation Field: {chunk.get('limitation')}")
            
            content = chunk.get('content', '')
            if "Limitation note 1" in content or "Limitation note 2" in content:
                found_limitation_text = True
            
            if chunk.get('migration_type') == 'slack__TO__teams':
                found_migration_type = True
                
            if chunk.get('limitation') in ["Limitation note 1", "Limitation note 2"]:
                found_limitation_field = True

        print("\n--- Verification Results ---")
        if found_limitation_text:
            print("[PASS] Limitation text found in content.")
        else:
            print("[FAIL] Limitation text NOT found in content.")

        if found_migration_type:
            print("[PASS] Migration type correctly assigned.")
        else:
            print("[FAIL] Migration type NOT assigned (or incorrect).")
            
        if found_limitation_field:
             print("[PASS] Limitation field populated in metadata.")
        else:
             print("[FAIL] Limitation field NOT populated.")

    finally:
        if os.path.exists(excel_file):
            os.remove(excel_file)
            print(f"Removed dummy Excel: {excel_file}")

if __name__ == "__main__":
    test_extraction()
