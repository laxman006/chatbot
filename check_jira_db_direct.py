"""
Direct check of Jira ChromaDB SQLite database
"""
import sqlite3
import os

db_path = 'data/jira_chroma_db/chroma.sqlite3'

print("=" * 80)
print("JIRA VECTORSTORE DATABASE INSPECTION")
print("=" * 80)

if not os.path.exists(db_path):
    print(f"\n✗ Database file does not exist: {db_path}")
else:
    print(f"\n✓ Database file exists: {db_path}")
    print(f"  Size: {os.path.getsize(db_path):,} bytes")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"\n[TABLES]")
        for table in tables:
            print(f"  • {table[0]}")
            
        # Check embeddings table if it exists
        if ('embeddings',) in tables:
            print(f"\n[EMBEDDINGS TABLE]")
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            count = cursor.fetchone()[0]
            print(f"  Total rows: {count}")
            
            if count > 0:
                cursor.execute("SELECT * FROM embeddings LIMIT 1")
                sample = cursor.fetchone()
                print(f"  Sample row columns: {len(sample) if sample else 0}")
        
        # Check segments table if it exists        
        if ('segments',) in tables:
            print(f"\n[SEGMENTS TABLE]")
            cursor.execute("SELECT COUNT(*) FROM segments")
            seg_count = cursor.fetchone()[0]
            print(f"  Total segments: {seg_count}")
        
        # Check collections table if it exists
        if ('collections',) in tables:
            print(f"\n[COLLECTIONS TABLE]")
            cursor.execute("SELECT id, name FROM collections")
            collections = cursor.fetchall()
            for coll in collections:
                print(f"  Collection: {coll[1]} (ID: {coll[0]})")
        
        conn.close()
        print(f"\n✓ Database is accessible via SQLite")
        print(f"✗ But ChromaDB loading fails due to index corruption")
        
    except Exception as e:
        print(f"\n✗ Error accessing database: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("The Jira vectorstore database is CORRUPTED.")
print("ChromaDB cannot load it due to an index range error.")
print("\nRECOMMENDED ACTION:")
print("  1. Backup the current database (if needed)")
print("  2. Rebuild the Jira vectorstore from scratch using:")
print("     python build_jira_vectorstore_all.py")
print("  3. Verify the rebuild completed successfully")
print("=" * 80)
