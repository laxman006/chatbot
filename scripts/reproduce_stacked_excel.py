import pandas as pd
import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.excel_processor import extract_excel_rows_as_chunks

def test_stacked_sections():
    # Simulate the user's data structure
    # Dataframe with "unnamed" columns effectively
    data = [
        # Section 1: Features (Standard)
        ["Features Included", "Status", "Description"], # explicit header row
        ["One Time Migration", "Yes", "Transfer channels and DMs"],
        ["Delta Migration", "Yes", "Incremental changes"],
        
        # Section 2: Out of Scope (Section Header Row)
        ["Out of scope features", None, None], 
        ["Custom emoji", "No", "Unique emojis"], # Has status
        
        # Section 3: Limitations (Section Header Row)
        ["Limitations", None, None],
        ["Reply messages will appear as new text", None, None], # Text in Col 0, others empty/nan
        ["Message previews are not migrated", "", ""]          # Text in Col 0, others empty string
    ]
    
    # Create DF with generic headers mimicking "read_excel" with no header=0
    # Or assuming header=0 was 'Features Included'
    
    # Let's verify how it looks if we treat row 0 as headers
    columns = ["Feature", "Supported", "Description"]
    df = pd.DataFrame(data[1:], columns=columns) # Skip first row, use it as cols for simulation
    
    # Actually, often 'Limitations' is just inserted in the middle.
    
    print("--- INPUT DATAFRAME ---")
    print(df)
    print("-----------------------")
    
    chunks = extract_excel_rows_as_chunks(df, "TestFile.xlsx", "Sheet1")
    
    print(f"\nExtracted {len(chunks)} chunks.\n")
    
    limitation_chunks = [c for c in chunks if c['chunk_type'] == 'limitation']
    feature_chunks = [c for c in chunks if c.get('chunk_type') != 'limitation'] # default is often None or 'feature' check impl dependent
    
    print(f"Feature Chunks: {len(feature_chunks)}")
    print(f"Limitation Chunks: {len(limitation_chunks)}")
    
    print("\n--- LIMITATION CHUNKS CONTENT ---")
    for c in limitation_chunks:
        print(f"[{c.get('chunk_type')}] {c.get('limitation')}")
        print(f"   -> Section: {c.get('section_title')}")

if __name__ == "__main__":
    test_stacked_sections()
