"""
Diagnostic: run a near_vector query against SharePointDocs (no RBAC, no filters).
Run from project root: python test_near_vector_query.py

If this returns 0, the issue is Weaviate/client/collection config.
If this returns >0, the issue is in the app (e.g. RBAC filter).
"""

import sys


def main():
    from app.weaviate_client import get_weaviate_client
    from app.weaviate_retriever import _get_embedding_model

    collection_name = "SharePointDocs"
    test_query = "what is cloudfuze"
    limit = 10

    print(f"[DIAG] near_vector query: collection={collection_name!r}, query={test_query!r}, limit={limit}")
    print("-" * 60)

    client = get_weaviate_client()
    if client is None:
        print("[ERROR] Weaviate client unavailable")
        return 1

    if not client.collections.exists(collection_name):
        print(f"[ERROR] Collection {collection_name!r} does not exist")
        return 1

    coll = client.collections.get(collection_name)
    model = _get_embedding_model()
    query_vector = model.embed_query(test_query)
    print(f"[OK] Query vector length: {len(query_vector)}")

    from weaviate.classes.query import MetadataQuery

    # 1) No target_vector, no filter
    try:
        resp = coll.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )
        n = len(resp.objects)
        print(f"[RESULT] near_vector (no target_vector, no filter): {n} objects")
        if n > 0:
            d = resp.objects[0].metadata.distance if resp.objects[0].metadata else None
            print(f"        first object distance: {d}")
    except Exception as e:
        print(f"[ERROR] near_vector (no target_vector): {e}")
        import traceback
        traceback.print_exc()

    # 2) With target_vector="default"
    try:
        resp2 = coll.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
            target_vector="default",
        )
        n2 = len(resp2.objects)
        print(f"[RESULT] near_vector (target_vector='default', no filter): {n2} objects")
        if n2 > 0:
            d2 = resp2.objects[0].metadata.distance if resp2.objects[0].metadata else None
            print(f"        first object distance: {d2}")
    except Exception as e:
        print(f"[ERROR] near_vector (target_vector='default'): {e}")
        import traceback
        traceback.print_exc()

    print("-" * 60)
    print("If both return 0: most objects in the collection likely have NO vectors.")
    print("  Startup count (53k) is total objects; near_vector only searches objects WITH vectors.")
    print("  Fix: re-ingest SharePoint docs with the current pipeline (embedding_service + batch_inserter)")
    print("       so every chunk gets a vector, or backfill vectors for existing objects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
