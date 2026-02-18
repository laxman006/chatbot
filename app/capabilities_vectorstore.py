"""
Dedicated ChromaDB for migration capabilities and limitations.

- Loads Chroma from CHROMA_CAPABILITIES_DB_PATH only (separate from main vectorstore).
- Use when the user asks about migration capabilities, limitations, supported/unsupported features.
- Integration: call is_capability_related_query(question); if True, get context from get_capability_docs(question)
  and use that context for the LLM (e.g. in your retrieval pipeline).
- Migration platform patterns: used to detect capability-related queries and to filter retrieval by migration_display.
"""

import os
import re
from typing import List, Optional, Any

# Same path as capability_limitations_ingest (dedicated DB only)
CHROMA_CAPABILITIES_DB_PATH = os.getenv("CHROMA_CAPABILITIES_DB_PATH", "./data/chroma_capabilities_db")

# Message/chat migration paths and content migration platform combinations (exact display names from Excel).
# Used to: (1) detect capability-related queries when user mentions any of these, (2) filter retrieval by migration_display.
# Order: message migrations first (Slack/Teams/Chat/Meta), then content migrations (Box, Dropbox, etc.).
MIGRATION_DISPLAY_PATTERNS = [
    # Message / chat migrations (Limitations and features.xlsx, message migrations sheets)
    "Slack to chat",
    "Slack to Teams",
    "Chat to Teams",
    "Teams to Chat",
    "Slack To Slack",
    "Teams to Teams",
    "Meta to Gchat",
    "Chat to Chat",
    "MS-Teams to Webex",
    # Content migrations
    "Box - One Drive for Business",
    "Box - Share Point Online",
    "Box - Google Suite",
    "Box - Google Shared Drive",
    "Box - Dropbox",
    "Box for business to Box for business",
    "Dropbox for Business - One Drive for Business",
    "Dropbox for Business - Share Point Online",
    "Dropbox for Business - Google Drive",
    "Dropbox for Business - Google Shared Drive",
    "Google Suite - One Drive for Business",
    "Google Suite - Share Point Online",
    "Google Suite - Google Suite",
    "Google Suite - Dropbox",
    "GSuite - Egnyte",
    "Gsuite - Box",
    "Shared Drive-Shared Drive",
    "Shared Drive- Share Point Online",
    "Citrix - One Drive for Business",
    "Citrix -Share Point Online",
    "Citrix -Google Suite",
    "Citrix - Shared Drive",
    "Egnyte - Onedrive for Business",
    "Egnyte - Sharepoint for Business",
    "Egnyte - Gsuite",
    "Egnyte - Gshared Drive",
    "Box - Citrix",
    "DropBox to Azure",
    "Dropbox to Box",
    "DropBox to egnyte",
    "Citrix - Citrix",
    "Shared Drive- Egnyte",
    "Shared Drive -  Onedrive",
    "Share point online - Shared Drive",
    "share point online - mydrive",
    "share point online - Share point online",
    "sharepint online -egnyte",
    "NFS - onedrive",
    "NFS - sharepoint online",
    "NFS t-mydrive",
    "NFS t--shared drive",
    "OneDrive to Amazon s3",
    "Box to Amazon s3",
    "SharePoint Online to Amazon S3",
    "Google Shared Drive to Amazon S3",
    "Sharefile to Amazon S3",
    "SharePoint Online to Azure",
    "Google Shared Drive to Azure",
    "Sharefile to Azure",
    "Dropbox to Azure",
    "Egnyte to Azure",
    "Amazon S3 to SharePoint Online",
    "Onedrive to- onedrive",
    "Onedrive-google mydrive",
    "Amazon workdocs to NFS",
    "Amazon wordocs to Sharepoint",
    "Amazon wordocs to OneDrive",
]


def _normalize_for_match(text: str) -> str:
    """Normalize text for substring matching: lowercase, collapse spaces and dashes."""
    if not text:
        return ""
    t = re.sub(r"[\s\-–—]+", " ", text.lower().strip())
    return " ".join(t.split())


def _query_mentions_migration(query: str, migration_display: str) -> bool:
    """True if the normalized query contains the migration (or key part of it) for filtering."""
    nq = _normalize_for_match(query)
    nm = _normalize_for_match(migration_display)
    if not nm or not nq:
        return False
    # Exact substring: migration name in query or query in migration
    if nm in nq or nq in nm:
        return True
    # Key part: first 3–4 words of migration (e.g. "box one drive" for "Box - One Drive for Business")
    words = nm.split()
    for length in range(min(4, len(words)), 1, -1):
        part = " ".join(words[:length])
        if len(part) >= 4 and part in nq:
            return True
    return False


def get_migrations_mentioned_in_query(query: str) -> List[str]:
    """
    Return list of migration_display values that are mentioned in the query.
    Used to filter capabilities Chroma by metadata so retrieval only returns chunks for those migrations.
    """
    if not query or not query.strip():
        return []
    mentioned = []
    for migration in MIGRATION_DISPLAY_PATTERNS:
        if _query_mentions_migration(query, migration):
            mentioned.append(migration)
    return mentioned

_capabilities_vectorstore = None


def preload_capabilities_vectorstore():
    """
    Load capabilities ChromaDB at startup so logs show whether the DB is available.
    Safe to call from async code (runs sync I/O). Call from server lifespan/startup.
    """
    return get_capabilities_vectorstore()


def get_capabilities_vectorstore():
    """Load the capabilities ChromaDB (lazy, cached). Returns None if DB does not exist."""
    global _capabilities_vectorstore
    if _capabilities_vectorstore is not None:
        return _capabilities_vectorstore
    if not os.path.isdir(CHROMA_CAPABILITIES_DB_PATH):
        print(f"[capabilities_vectorstore] DB path not found: {CHROMA_CAPABILITIES_DB_PATH} (run scripts/ingest_capability_limitations.py to create)")
        return None
    try:
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        _capabilities_vectorstore = Chroma(
            persist_directory=CHROMA_CAPABILITIES_DB_PATH,
            embedding_function=embeddings,
            collection_metadata={"hnsw:space": "cosine"},
        )
        print(f"[capabilities_vectorstore] Loaded from {CHROMA_CAPABILITIES_DB_PATH}")
        return _capabilities_vectorstore
    except Exception as e:
        print(f"[capabilities_vectorstore] Failed to load: {e}")
        return None


def get_capabilities_retriever(k: int = 15):
    """Return a retriever over the capabilities ChromaDB. Returns None if DB not available."""
    vs = get_capabilities_vectorstore()
    if vs is None:
        return None
    return vs.as_retriever(search_type="similarity", search_kwargs={"k": k})


# Keywords that suggest the question is about migration capabilities/limitations
# - Generic: capability, limitation, supported, migration support/feature, etc.
# - Migration combinations (source → target): slack to teams, teams to chat, slack to google chat, box to onedrive.
# - Platform names (single source/target, not combinations): onedrive, sharepoint, google drive, dropbox, egnyte, citrix, etc.
# - Question patterns: "is X possible", "does X support", "can X migrate"
_CAPABILITY_KEYWORDS = re.compile(
    r"\b(migration\s+(capabilit|support|feature|limit)|"
    r"capabilit|limitation|supported|unsupported|not\s+support|"
    r"delta\s+migration|one\s*time\s+migration|"
    r"slack\s+to\s+teams|teams\s+to\s+chat|slack\s+to\s+google\s+chat|box\s+to\s+onedrive|"
    r"onedrive|sharepoint|google\s+drive|dropbox|box\s+for\s+business|"
    r"egnyte|citrix|shared\s+drive|content\s+migration|"
    r"is\s+.*\s+possible|does\s+.*\s+support|can\s+.*\s+migrate)\b",
    re.IGNORECASE,
)


def is_capability_related_query(query: str) -> bool:
    """True if the query is likely about migration capabilities/limitations (keywords or migration platform names)."""
    if not query or not query.strip():
        return False
    q = query.strip()
    if _CAPABILITY_KEYWORDS.search(q):
        return True
    # Also true if user mentions any known migration platform (from content Excel list)
    if get_migrations_mentioned_in_query(q):
        return True
    return False


def is_capability_related_query_llm(query: str, llm: Any) -> bool:
    """
    Use LLM to classify whether the query is about migration capabilities/limitations
    (same style as intelligent query routing). Use when routing_plan is not available (e.g. fallback path).
    """
    if not query or not query.strip():
        return False
    prompt = """Is this user question about migration capabilities, supported/unsupported features, or limitations?
Examples: "what are the limitations of slack to chat", "can we migrate pinned messages", "does CloudFuze support X", "what features are supported for Slack to Teams".
Answer with exactly one word: yes or no.

Question: """
    try:
        response = llm.invoke(prompt + query.strip())
        content = (response.content if hasattr(response, "content") else str(response)).strip().lower()
        return content.startswith("yes")
    except Exception as e:
        print(f"[capabilities_vectorstore] LLM capability check failed: {e}, falling back to regex")
        return is_capability_related_query(query)


def get_capability_docs(query: str, k: int = 15, force: bool = False) -> List:
    """
    If the query is capability-related, return docs from the capabilities ChromaDB; else return [].

    When the query mentions specific migration(s) from MIGRATION_DISPLAY_PATTERNS, retrieval is filtered
    by metadata (migration_display) so only chunks for those migrations are returned.

    force: if True, skip the capability-related check (caller already decided, e.g. via LLM).
    Returns list of LangChain Documents (or empty list). Use these as context for the LLM when
    answering capability/limitation questions.
    """
    if not force and not is_capability_related_query(query):
        return []
    vs = get_capabilities_vectorstore()
    if vs is None:
        return []
    try:
        mentioned = get_migrations_mentioned_in_query(query)
        # Log so retrieval logs show capabilities ChromaDB is being queried
        print(f"[capabilities_vectorstore] Querying ChromaDB (k={k}, migration_filter={mentioned or 'none'})")
        if mentioned:
            # Filter by migration_display so we only get chunks for the migration(s) the user asked about
            if len(mentioned) == 1:
                where = {"migration_display": mentioned[0]}
            else:
                where = {"migration_display": {"$in": mentioned}}
            docs_with_scores = vs.similarity_search_with_score(query, k=k, filter=where)
            # If filter returns 0 (e.g. no chunks for "Meta to Gchat" in DB), fall back to unfiltered so we still return some capability docs
            if not docs_with_scores:
                print(f"[capabilities_vectorstore] Filtered search returned 0 docs for migration_display={mentioned}, falling back to unfiltered")
                docs_with_scores = vs.similarity_search_with_score(query, k=k)
        else:
            docs_with_scores = vs.similarity_search_with_score(query, k=k)
        return [doc for doc, _ in docs_with_scores]
    except Exception as e:
        print(f"[capabilities_vectorstore] Retrieval failed: {e}")
        return []
