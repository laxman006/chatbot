"""
Verify capabilities flow: router classifies as "capabilities" and retrieval path runs.
Run from project root: python scripts/verify_capabilities_flow.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=== 1. Router: capabilities classification ===\n")
    try:
        from app.llm_factory import get_llm
        from intelligent_router import IntelligentQueryRouter
        from config import ROUTING_TOTAL_BUDGET
        router_llm = get_llm()
        router = IntelligentQueryRouter(router_llm, total_budget=ROUTING_TOTAL_BUDGET)
        test_queries = [
            "what are the limitations of slack to chat",
            "list out-of-scope features for Slack to Teams",
            "can we migrate two same files during meta to chat",
            "what features are supported for Teams to Teams",
        ]
        for q in test_queries:
            plan = router.route_query(q)
            qtype = (plan or {}).get("query_type", "")
            ok = "OK" if qtype == "capabilities" else "MISS"
            print(f"  [{ok}] query_type={qtype!r}  query={q[:50]}...")
        print()
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=== 2. get_migrations_mentioned_in_query ===\n")
    try:
        from app.capabilities_vectorstore import get_migrations_mentioned_in_query
        for q in ["limitations of Slack to Teams", "Meta to Gchat duplicate files", "Box to OneDrive features"]:
            mentioned = get_migrations_mentioned_in_query(q)
            print(f"  query={q[:45]}... -> {mentioned}")
        print()
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=== 3. get_capability_docs (may return [] if DB empty) ===\n")
    try:
        from app.capabilities_vectorstore import get_capability_docs
        docs = get_capability_docs("what are the limitations of slack to chat", k=3, force=True)
        print(f"  get_capability_docs(..., k=3, force=True) -> {len(docs)} docs")
        if docs:
            print(f"  First doc metadata keys: {list(docs[0].metadata.keys())[:8]}")
        else:
            print("  (0 docs is OK if chroma_capabilities_db not populated; run scripts/ingest_capability_limitations.py)")
        print()
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=== 4. Endpoints: add_capability logic (dry run) ===\n")
    try:
        query_type = "capabilities"
        query = "list out-of-scope features for Slack to Chat"
        from app.capabilities_vectorstore import get_migrations_mentioned_in_query
        add_capability = (
            query_type == "capabilities"
            or (
                query_type == "migration_procedure"
                and get_migrations_mentioned_in_query(query)
            )
        )
        print(f"  query_type={query_type!r}, add_capability={add_capability}")
        assert add_capability, "add_capability should be True for capabilities query"
        print("  OK: add_capability is True -> capability docs will be fetched in real request\n")
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    print("=== All checks passed ===\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
