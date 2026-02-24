"""
Dedicated ChromaDB for migration capabilities and limitations.

- Loads Chroma from CHROMA_CAPABILITIES_DB_PATH only (separate from main vectorstore).
- Use when the user asks about migration capabilities, limitations, supported/unsupported features.
- Integration: call is_capability_related_query(question); if True, get context from get_capability_docs(question)
  and use that context for the LLM (e.g. in your retrieval pipeline).
- Filter logic: migrations are matched by (source, destination) only. Query is parsed into source and destination
  using platform aliases; a migration is included only when BOTH its source and destination match the query's.
"""

import os
import re
from typing import List, Optional, Any, Tuple

# Same path as capability_limitations_ingest (dedicated DB only)
CHROMA_CAPABILITIES_DB_PATH = os.getenv("CHROMA_CAPABILITIES_DB_PATH", "./data/chroma_capabilities_db")

# ---------------------------------------------------------------------------
# Platform canonical keys and aliases for (source, destination) matching.
# Each canonical key maps to a list of aliases (including itself). When we
# parse a display name or query, we normalize to the canonical key so that
# "Box to Citrix" matches only "Box - Citrix", not "Box to Amazon s3".
# Order: longer phrases first so "one drive for business" matches before "drive".
# ---------------------------------------------------------------------------
_PLATFORM_CANONICAL_ALIASES: List[Tuple[str, List[str]]] = [
    ("one drive for business", ["one drive for business", "onedrive", "odfb", "one drive", "onedrive for business"]),
    ("share point online", ["share point online", "sharepoint", "sharepoint online", "sharepoint for business", "sharepint online"]),
    ("google suite", ["google suite", "gsuite", "google workspace"]),
    ("google shared drive", ["google shared drive", "gshared drive", "google shared drives"]),
    ("shared drive", ["shared drive", "shared drives"]),
    ("dropbox for business", ["dropbox for business"]),
    ("dropbox", ["dropbox", "drop box"]),
    ("box for business", ["box for business"]),
    ("box", ["box"]),
    ("egnyte", ["egnyte"]),
    ("citrix", ["citrix"]),
    ("amazon s3", ["amazon s3", "s3"]),
    ("azure", ["azure"]),
    ("nfs", ["nfs"]),
    ("mydrive", ["mydrive", "my drive", "google mydrive", "google my drive"]),
    ("sharefile", ["sharefile", "share file"]),
    ("amazon workdocs", ["amazon workdocs", "workdocs"]),
    ("amazon wordocs", ["amazon wordocs", "wordocs"]),
    # Message migrations
    ("slack", ["slack"]),
    ("teams", ["teams", "ms-teams", "msteams"]),
    ("chat", ["chat", "google chat"]),
    ("gchat", ["gchat", "google chat"]),
    ("meta", ["meta"]),
    ("webex", ["webex"]),
]
# Build alias -> canonical (longest alias wins when multiple canonicals share a substring; we match longest first in query)
_ALIAS_TO_CANONICAL: dict = {}
for canonical, aliases in _PLATFORM_CANONICAL_ALIASES:
    for a in aliases:
        a_clean = " ".join(a.lower().strip().split())
        if a_clean not in _ALIAS_TO_CANONICAL or len(a_clean) > len(_ALIAS_TO_CANONICAL.get(a_clean, "")):
            _ALIAS_TO_CANONICAL[a_clean] = canonical
# Ensure each canonical maps to itself
for canonical, _ in _PLATFORM_CANONICAL_ALIASES:
    c_clean = " ".join(canonical.lower().split())
    _ALIAS_TO_CANONICAL[c_clean] = canonical
# Sorted list of (phrase, canonical) by phrase length desc for longest-match-first when scanning query
_match_list: List[Tuple[str, str]] = []
for canonical, aliases in _PLATFORM_CANONICAL_ALIASES:
    for a in aliases:
        p = " ".join(a.lower().strip().split())
        if p:
            _match_list.append((p, canonical))
_match_list.sort(key=lambda x: -len(x[0]))
# Dedupe by phrase (same phrase may appear in multiple canonicals; keep first = longest canonical match)
_seen_phrase: dict = {}
for phrase, canonical in _match_list:
    if phrase not in _seen_phrase:
        _seen_phrase[phrase] = canonical
_MATCH_PHRASES = sorted([(p, c) for p, c in _seen_phrase.items()], key=lambda x: -len(x[0]))

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


def _token_to_canonical(token: str) -> str:
    """Normalize a single platform token to its canonical key using alias map."""
    if not token or not token.strip():
        return ""
    t = " ".join(token.lower().strip().split())
    return _ALIAS_TO_CANONICAL.get(t, t)


def _parse_migration_display(display: str) -> Tuple[str, str]:
    """
    Parse a migration display name into (source_canonical, dest_canonical).
    Splits on ' - ' or ' to ' (flexible spacing). Returns ("", "") if not exactly two parts.
    """
    if not display or not display.strip():
        return ("", "")
    # Normalize " to " to " - " so we have one split pattern
    normalized = re.sub(r"\s+to\s+", " - ", display.strip(), flags=re.IGNORECASE)
    parts = re.split(r"\s*[-–—]\s*", normalized, maxsplit=1)
    if len(parts) != 2:
        return ("", "")
    src = _token_to_canonical(parts[0].strip())
    dst = _token_to_canonical(parts[1].strip())
    return (src, dst)


# List of (source_canonical, dest_canonical, display_name) for strict (source, dest) matching
MIGRATION_SOURCE_DEST: List[Tuple[str, str, str]] = []
for _disp in MIGRATION_DISPLAY_PATTERNS:
    _s, _d = _parse_migration_display(_disp)
    if _s and _d:
        MIGRATION_SOURCE_DEST.append((_s, _d, _disp))


def _extract_source_dest_from_query(query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (source_canonical, dest_canonical) from the query by finding platform mentions in order.
    Uses longest-match-first so "one drive for business" matches before "drive".
    Returns (None, None) if we don't find at least two distinct platforms in order.
    """
    if not query or not query.strip():
        return (None, None)
    q = " ".join(query.lower().strip().split())
    # Replace " to " with space so "box to citrix" becomes "box citrix" and we still find both
    q = re.sub(r"\s+to\s+", " ", q)
    q = re.sub(r"\s+[-–—]\s+", " ", q)
    # Find all (start_index, canonical) for each phrase that appears in q, longest first
    matches: List[Tuple[int, str]] = []
    for phrase, canonical in _MATCH_PHRASES:
        start = 0
        while True:
            idx = q.find(phrase, start)
            if idx == -1:
                break
            end = idx + len(phrase)
            matches.append((idx, end, canonical))
            start = idx + 1
    # Sort by start index; drop overlapping matches (keep first occurrence by position)
    matches.sort(key=lambda x: x[0])
    non_overlapping: List[Tuple[int, int, str]] = []
    for idx, end, canonical in matches:
        if non_overlapping and idx < non_overlapping[-1][1]:
            continue
        non_overlapping.append((idx, end, canonical))
    if len(non_overlapping) < 2:
        return (None, None)
    return (non_overlapping[0][2], non_overlapping[1][2])


def get_migrations_mentioned_in_query(query: str) -> List[str]:
    """
    Return list of migration_display values that match the query by (source, destination) only.
    Used to filter capabilities Chroma by metadata so retrieval only returns chunks for those migrations.
    E.g. "Box to Citrix" returns only ["Box - Citrix"], not "Box to Amazon s3".
    """
    if not query or not query.strip():
        return []
    q_src, q_dst = _extract_source_dest_from_query(query)
    if q_src is None or q_dst is None:
        return []
    return [
        display_name
        for (ms, md, display_name) in MIGRATION_SOURCE_DEST
        if (ms, md) == (q_src, q_dst)
    ]


def get_query_combination_canonical(query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (source_canonical, target_canonical) from the query for combination-based filtering.
    Returns (None, None) if the query does not mention a migration direction.
    Use with parse_combination_to_canonical() to compare doc metadata.
    """
    return _extract_source_dest_from_query(query or "")


def parse_combination_to_canonical(display: str) -> Tuple[str, str]:
    """
    Parse a combination or migration_display string into (source_canonical, target_canonical).
    Handles formats like "Egnyte - SharePoint", "MyDrive to OneDrive", "Box - One Drive for Business".
    Returns ("", "") if display is empty or cannot be parsed into two parts.
    """
    return _parse_migration_display(display or "")


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
        if not docs_with_scores:
            print(f"[capabilities_vectorstore] ChromaDB returned 0 documents (collection may be empty — run scripts/ingest_capability_limitations.py on this host)")
        return [doc for doc, _ in docs_with_scores]
    except Exception as e:
        print(f"[capabilities_vectorstore] Retrieval failed: {e}")
        return []
