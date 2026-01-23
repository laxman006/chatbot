"""Query SQLite database directly to check contents."""
import sqlite3
import os

db_path = "./data/jira_chroma_db/chroma.sqlite3"

if not os.path.exists(db_path):
    print(f"[ERROR] Database not found: {db_path}")
    exit(1)

print("=" * 70)
print("SQLITE DATABASE DIRECT QUERY")
print("=" * 70)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"\n[OK] Database connected successfully")
    print(f"[OK] Database file size: {os.path.getsize(db_path) / (1024**3):.2f} GB")
    print(f"\n[OK] Tables in database:")
    for table in tables:
        print(f"     - {table[0]}")
    
    # Check embeddings table
    if any('embeddings' in str(t).lower() for t in tables):
        try:
            cursor.execute("SELECT COUNT(*) FROM embeddings;")
            count = cursor.fetchone()[0]
            print(f"\n[OK] Total embeddings/documents: {count:,}")
        except Exception as e:
            print(f"\n[ERROR] Could not query embeddings: {e}")
    
    # Check collections table
    try:
        cursor.execute("SELECT COUNT(*) FROM collections;")
        collections_count = cursor.fetchone()[0]
        print(f"[OK] Collections: {collections_count}")
    except Exception as e:
        print(f"[WARN] Collections table issue: {e}")
    
    conn.close()
    
    print(f"\n{'=' * 70}")
    print("RECOMMENDATION")
    print(f"{'=' * 70}")
    
    if os.path.getsize(db_path) > 500 * 1024 * 1024:  # > 500MB
        print("[WARN] Database is unusually large (> 500MB)")
        print("       Expected size for 25K chunks: ~200-300MB")
        print("       This suggests accumulated builds or corruption")
        print("\n[RECOMMENDATION] Rebuild from scratch for clean state")
    
except Exception as e:
    print(f"\n[ERROR] Could not query database: {e}")
    print(f"\n[INFO] Database appears to be corrupted")
    print(f"[RECOMMENDATION] Rebuild from scratch")
    import traceback
    traceback.print_exc()
