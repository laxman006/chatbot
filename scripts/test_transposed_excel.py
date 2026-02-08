import os
import sys
import pandas as pd
from typing import List, Dict

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.excel_processor import extract_excel_rows_as_chunks

def create_transposed_excel(filename: str):
    """Create a dummy Excel file with Transposed format (Row=Migration, Col=Feature)."""
    data = {
        "Cloud Combination/Features": ["Box - One Drive", "Slack - Teams"],
        "OneTime": ["Yes", "No"],
        "Delta": ["Yes", "Yes"],
        "Permissions": ["No", "Yes"]
    }
    df = pd.DataFrame(data)
    file_path = os.path.abspath(filename)
    with pd.ExcelWriter(file_path) as writer:
        df.to_excel(writer, sheet_name="Box Migrations", index=False)
    print(f"Created transposed Excel: {file_path}")
    return file_path

def test_transposed_extraction():
    excel_file = "test_transposed.xlsx"
    try:
        excel_path = create_transposed_excel(excel_file)
        
        print(f"Extracting chunks from: {excel_path}")
        chunks = extract_excel_rows_as_chunks(excel_path)
        
        print(f"Extracted {len(chunks)} chunks.")
        
        found_matrix_data = False
        
        for i, chunk in enumerate(chunks):
            print(f"--- Chunk {i} ---")
            print(f"Type: {chunk.get('chunk_type')}")
            print(f"Content: {chunk.get('content')}")
            print(f"Feature: {chunk.get('feature')}")
            print(f"Migration Type: {chunk.get('migration_type')}")
            
            # We want to see if it correctly identified "OneTime" as a feature for "Box - One Drive" migration
            content = chunk.get('content', '')
            if "Migration: Box - One Drive" in content and "Feature: OneTime" in content:
                found_matrix_data = True

        print("\n--- Verification Results ---")
        if found_matrix_data:
            print("[PASS] Transposed matrix data correctly extracted.")
        else:
            print("[FAIL] Transposed matrix data NOT extracted as migration capabilities.")

    finally:
        if os.path.exists(excel_file):
            os.remove(excel_file)
            print(f"Removed dummy Excel: {excel_file}")

if __name__ == "__main__":
    test_transposed_extraction()
