# -*- coding: utf-8 -*-
"""
Intelligent Query Router - LLM-Powered Dynamic Multi-Source Retrieval

This module uses an LLM to analyze user queries and dynamically allocate
retrieval budget across multiple knowledge sources (Jira, Blog, SharePoint, etc.)
"""

from typing import Dict, List, Tuple, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
import json
import re
from config import (
    ROUTING_TOTAL_BUDGET,
    ROUTING_MIN_CONFIDENCE,
    MAX_JIRA_K, MAX_BLOG_K, MAX_SHAREPOINT_K,
    MAX_PDF_K, MAX_TRANSCRIPT_K, MAX_EXCEL_K,
    MAX_LIMITATIONS_K,
)


class IntelligentQueryRouter:
    """
    LLM-powered query router that dynamically allocates retrieval across sources.
    
    Analyzes query intent and determines:
    1. Which knowledge sources are most relevant
    2. How many documents to retrieve from each source
    3. Reasoning for allocation decisions
    """
    
    def __init__(self, llm, total_budget: int = None):
        """
        Initialize the query router.
        
        Args:
            llm: Language model instance for routing decisions
            total_budget: Total number of documents to retrieve (default from config)
        """
        self.llm = llm
        self.total_budget = total_budget or ROUTING_TOTAL_BUDGET
        
        # Define available sources and their characteristics
        self.sources = {
            "blog": {
                "description": "Marketing blog posts (customer-facing) - contains product announcements, migration guides, how-to articles, but primarily marketing content. Use sparingly for internal team members.",
                "typical_use": "Last resort for general product information when internal docs unavailable. Extract technical facts only, ignore marketing language.",
                "max_k": MAX_BLOG_K
            },
            "sharepoint": {
                "description": "Internal documentation, policies, SOC certificates, compliance docs, security documents, official forms, internal procedures, setup guides - PRIMARY SOURCE for internal team",
                "typical_use": "Compliance, security, certificates, internal policies, official documentation, legal documents, internal procedures, team resources",
                "max_k": MAX_SHAREPOINT_K
            },
            "jira": {
                "description": "Resolved support tickets (PRI-XXXX, CF-XXXX) with bug fixes, error resolutions, troubleshooting steps, known issues, root causes, workarounds, edge cases, customer-specific incidents, project/server-specific issues (epiqglobal2, lgads2, etc.) - PRIMARY SOURCE for troubleshooting",
                "typical_use": "Error troubleshooting, bug resolutions, known issues, workarounds, technical problems, past incidents, error messages, migration failures, edge cases, ticket lookups, version conflicts, retry operations, specific customer issues",
                "max_k": MAX_JIRA_K
            },
            "transcripts": {
                "description": "Cloudfuze manage sales call transcripts, customer conversations, Q&A sessions, objection handling, real discussions, customer requirements - useful for sales team context",
                "typical_use": "Cloudfuze manage sales scenarios, customer objections, feature discussions, real-world conversations, use cases, customer requirements (for sales team)",
                "max_k": MAX_TRANSCRIPT_K
            },
            "pdfs": {
                "description": "Technical documentation, user guides, API docs, detailed specifications, architecture documents, technical references - PRIMARY SOURCE for technical details",
                "typical_use": "In-depth technical documentation, detailed guides, API references, technical specs, architectural details",
                "max_k": MAX_PDF_K
            },
            "excel": {
                "description": "Structured data, pricing tables, feature comparisons, migration checklists, data matrices, feature matrices",
                "typical_use": "Pricing information, structured comparisons, data tables, feature matrices, checklists",
                "max_k": MAX_EXCEL_K
            },
            "limitations": {
                "description": "Limitations & Supported Features (SharePoint) - definitive source for what is supported/not supported, out-of-scope features, migration capabilities per combination (e.g. Slack to Teams, Slack to Chat). Same role as Jira for troubleshooting.",
                "typical_use": "Supported/unsupported features, limitations, out-of-scope, 'can we migrate X', 'does CloudFuze support Y', 'what is supported/not supported' for any migration combination. Use when query_type is capabilities.",
                "max_k": MAX_LIMITATIONS_K
            }
        }
    
    def _is_who_is_question(self, query: str) -> bool:
        """
        Check if query is asking "who is" about a person.
        
        Args:
            query: User query string
            
        Returns:
            True if query matches "who is" pattern asking about a person
        """
        query_lower = query.lower().strip()
        # Pattern: "who is" followed by a name/person identifier
        # Handles variations like "who is", "who's", with optional punctuation/question marks
        # Matches: "who is nirosh", "who's john", "who is nivas?", etc.
        pattern = r'^who[\'s]?\s+is\s+\w+'
        if re.match(pattern, query_lower):
            print(f"[ROUTER] Detected 'who is' question: {query}")
            return True
        return False
    
    def route_query(self, query: str) -> Dict:
        """
        Use LLM to determine optimal retrieval strategy.
        
        Args:
            query: User query string
            
        Returns:
            Routing plan dictionary with source allocations:
            {
                "query_type": "troubleshooting|general_info|compliance|sales|technical",
                "query_intent": "brief summary",
                "sources": {
                    "blog": {"relevance": 0.8, "k": 15, "reasoning": "..."},
                    "jira": {"relevance": 0.9, "k": 20, "reasoning": "..."},
                    ...
                },
                "confidence": 0.0-1.0
            }
        """
        
        # Build source descriptions
        source_descriptions = "\n".join([
            f"- **{name}**: {info['description']}\n"
            f"  Typical use: {info['typical_use']}\n"
            f"  Max documents: {info['max_k']}"
            for name, info in self.sources.items()
        ])
        
        system_prompt = f"""You are an intelligent query routing system for a RAG (Retrieval Augmented Generation) chatbot about CloudFuze - a cloud migration and data management platform.

**CRITICAL: This chatbot is for INTERNAL CloudFuze team members (developers, QA, sales, support), NOT customers.**

**Available Knowledge Sources:**
{source_descriptions}

**Your Task:**
Analyze the user query and determine:
1. Which sources are most relevant (relevance score 0.0-1.0)
2. How many documents to retrieve from each source (k value)
3. Why each source is or isn't relevant

**Guidelines:**
- Total documents budget: {self.total_budget} (distribute across sources)
- Higher relevance = more documents allocated
- Multiple sources can be relevant (e.g., jira + sharepoint for internal procedures)
- If a source is irrelevant, set relevance=0.0 and k=0
- BE GENEROUS with retrieval - better to retrieve too much than miss relevant content
- **PRIORITIZE INTERNAL SOURCES** (Jira, SharePoint, PDFs) over blog posts
- **Blog posts are LOW PRIORITY** - only use when internal docs don't have the information

- Consider query type:
  * **Troubleshooting/Errors** → Prioritize Jira (0.8-1.0), SharePoint (0.4-0.6), PDFs (0.4-0.6), blog (0.2-0.4) ONLY if needed
  * **Ticket Lookups/Queries** → Prioritize Jira (0.9-1.0), set k=30
  * **Migration Procedures** (during migration, changing settings, modify config) → Prioritize SharePoint (0.7-0.9), Jira (0.6-0.8), PDFs (0.5-0.7), blog (0.2-0.4) ONLY if internal docs unavailable
  * **General info** → Prioritize SharePoint (0.6-0.8), PDFs (0.5-0.7), Jira (0.3-0.5), blog (0.2-0.4) ONLY if needed
  * **Configuration/Setup** → Prioritize SharePoint (0.7-0.9), PDFs (0.6-0.8), Jira (0.4-0.6), blog (0.2-0.3) ONLY if needed
  * **Compliance/Security** → Prioritize SharePoint (0.9-1.0), PDFs (0.3-0.5), blog (0.1-0.2) ONLY if needed
  * **Sales scenarios** → Prioritize transcripts (0.7-1.0), SharePoint (0.4-0.6), blog (0.2-0.4) ONLY if needed
  * **Technical deep-dive** → Prioritize PDFs (0.8-1.0), SharePoint (0.5-0.7), Jira (0.4-0.6), blog (0.1-0.3) ONLY if needed
  * **Pricing** → Prioritize excel (0.8-1.0), transcripts (0.5-0.7), SharePoint (0.3-0.5), blog (0.1-0.2) ONLY if needed
  * **Best practices** → Prioritize SharePoint (0.6-0.8), Jira (0.5-0.7), transcripts (0.4-0.6), blog (0.2-0.4) ONLY if needed
  * **Capabilities/Limitations** → Use query_type: **capabilities** when the user asks about: feature capabilities, migration limitations, out-of-scope features, supported/unsupported features, "can we migrate X", "does CloudFuze support Y", "what are the limitations/features/capabilities of [combination]", "list out-of-scope features", "what is supported/not supported" for any migration combination (e.g. Slack to Teams, Slack to Chat, Meta to Gchat, Teams to Teams, Box to OneDrive). Allocate to **limitations** (0.8-1.0, k=4-6) - this is the definitive Limitations & Supported Features source. Also use SharePoint (0.7-0.9), PDFs (0.6-0.8), Jira (0.4-0.6), blog (0.2-0.4).
- Look for signals even if keywords are missing (copy-pasted errors, stack traces, failure descriptions)

**Important Query Understanding:**
- If query describes an error/problem WITHOUT using words like "error" or "fix", still detect it
- If query contains technical failure symptoms, prioritize Jira heavily
- If query is copy-pasted error message/logs, prioritize Jira heavily
- Queries about "during migration", "ongoing migration", "while migrating" are migration_procedure type
- Queries about changing/modifying files, configs, settings during migration need SharePoint + Jira (not blog)
- If query mentions specific error messages or failures, prioritize Jira
- Be generous with k values for internal sources - better to over-retrieve than return 0 results
- **Blog should rarely get k > 3** - only when internal sources truly don't have the information
- **Default blog allocation should be k=0-2** - only allocate if query is clearly about marketing/public content

**🚫 JIRA EXCLUSION PATTERNS:**
Queries MUST NOT route to Jira (set relevance=0.0, k=0) if they are:
- **"Who is" questions**: Queries asking "who is [name]" about a person - these are about people, not tickets. Use SharePoint or other internal docs instead.

**🎯 JIRA-SPECIFIC PATTERNS (HIGH PRIORITY):**
Queries MUST route primarily to Jira (relevance ≥ 0.8, k ≥ 25) if they contain:
- **Ticket numbers**: PRI-XXXX, CF-XXXX, SUPPORT-XXXX, etc.
- **Server/Project names with numbers**: epiqglobal2, lgads2, roccofortehotel2, pilottravelcenters, willowwealth2, etc.
- **"How many tickets"**: Questions asking for ticket counts or lists
- **"Show/List/Find tickets"**: Queries requesting ticket information
- **"Retry" + specific names**: "retry file version for X", "retry all versions X"
- **"Version conflicts" + names**: Mentions of version issues with specific entities
- **"Migration failed/issues" + specific names**: Migration problems for named projects
- **Root cause/Fix description requests**: "What was the root cause of X", "How was X fixed"
- **Ticket-related verbs**: "resolved", "fixed", "closed", "worked on", "ticket for"

**Pattern Examples for Jira:**
- "how many tickets are related to epiqglobal2" → Jira (relevance=1.0, k=30)
- "What is the retry file version for epiqglobal2?" → Jira (relevance=0.9, k=30)
- "PRI-9812 details" → Jira (relevance=1.0, k=30)
- "Show me tickets for Box to OneDrive" → Jira (relevance=0.9, k=25)
- "retry all file versions lgads2" → Jira (relevance=0.95, k=30)
- "version conflicts in roccofortehotel2" → Jira (relevance=0.9, k=25)

**Query Type Examples:**
- "how to change CSV during migration" → migration_procedure (SharePoint: high, Jira: medium, blog: low)
- "migration failed with error 500" → troubleshooting (Jira: high, SharePoint: medium, blog: very low)
- "what is CloudFuze" → general_info (SharePoint: high, PDFs: medium, blog: low)
- "what are the limitations of slack to chat" → capabilities (limitations: high k=4-6, SharePoint: high, PDFs: high, blog: low)
- "list out-of-scope features for Slack to Chat" → capabilities (limitations: high k=4-6, SharePoint: high, PDFs: high, Jira: medium, blog: low)
- "can we migrate pinned messages from slack to google chat" → capabilities (limitations: high k=4-6, SharePoint: high, PDFs: high, blog: low)
- "what features are supported for Meta to Gchat / Teams to Teams / Box to OneDrive" → capabilities (limitations: high k=4-6, SharePoint: high, PDFs: high, Jira: medium, blog: low)
- "SOC 2 certification" → compliance (SharePoint: high, blog: very low)
- "customer objection about pricing" → sales (transcripts: high, SharePoint: medium, blog: low)
- "API rate limits" → technical (PDFs: high, SharePoint: medium, blog: very low)

**Respond in JSON format:**
{{
  "query_type": "troubleshooting|general_info|migration_procedure|configuration|compliance|sales|technical|pricing|best_practices|capabilities",
  "query_intent": "brief summary of what user wants (1 sentence)",
  "sources": {{
    "blog": {{"relevance": 0.0-1.0, "k": 0-{MAX_BLOG_K}, "reasoning": "why/why not (remember: low priority for internal users)"}},
    "sharepoint": {{"relevance": 0.0-1.0, "k": 0-{MAX_SHAREPOINT_K}, "reasoning": "why/why not"}},
    "jira": {{"relevance": 0.0-1.0, "k": 0-{MAX_JIRA_K}, "reasoning": "why/why not"}},
    "transcripts": {{"relevance": 0.0-1.0, "k": 0-{MAX_TRANSCRIPT_K}, "reasoning": "why/why not"}},
    "pdfs": {{"relevance": 0.0-1.0, "k": 0-{MAX_PDF_K}, "reasoning": "why/why not"}},
    "excel": {{"relevance": 0.0-1.0, "k": 0-{MAX_EXCEL_K}, "reasoning": "why/why not"}},
    "limitations": {{"relevance": 0.0-1.0, "k": 0-{MAX_LIMITATIONS_K}, "reasoning": "why/why not - use for support/capabilities/limitations questions only"}}
  }},
  "confidence": 0.0-1.0
}}

**Budget Constraint:** Sum of all k values should be ≤ {self.total_budget}
**Remember:** Blog posts are marketing content - use sparingly (typically k ≤ 5) and only when internal sources don't have the information.
"""

        user_message = f"""Query: "{query}"

Analyze this query and determine the optimal retrieval strategy. Consider:
1. What is the user trying to achieve?
2. Which sources would have the most relevant information?
3. How should I allocate the {self.total_budget} document budget across sources?
4. Is this describing a problem/error even without explicit keywords?"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            
            response = self.llm.invoke(messages)
            result_text = response.content.strip()
            
            # Parse JSON response
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            routing_plan = json.loads(result_text)
            
            # Validate and normalize
            routing_plan = self._validate_routing_plan(routing_plan, query)
            
            # Exclude Jira for "who is" questions
            if self._is_who_is_question(query):
                if "jira" in routing_plan.get("sources", {}):
                    routing_plan["sources"]["jira"]["k"] = 0
                    routing_plan["sources"]["jira"]["relevance"] = 0.0
                    routing_plan["sources"]["jira"]["reasoning"] = "Excluded - 'who is' questions don't need Jira tickets"
            
            # Log routing decision
            self._log_routing_decision(query, routing_plan)
            
            return routing_plan
            
        except Exception as e:
            print(f"[ERROR] LLM routing failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to balanced retrieval
            return self._get_fallback_routing(query)
    
    def _validate_routing_plan(self, plan: Dict, query: Optional[str] = None) -> Dict:
        """
        Validate and normalize routing plan.
        
        - Enforces budget constraints
        - Applies source-specific k limits
        - Ensures at least some retrieval happens
        """
        sources = plan.get("sources", {})
        
        # Apply source-specific max k limits
        for source_name in sources:
            max_k = self.sources.get(source_name, {}).get("max_k", 20)
            if sources[source_name].get("k", 0) > max_k:
                print(f"[ROUTER] Capping {source_name} k from {sources[source_name]['k']} to {max_k}")
                sources[source_name]["k"] = max_k
        
        # Calculate total k
        total_k = sum(src.get("k", 0) for src in sources.values())
        
        # If over budget, scale down proportionally
        if total_k > self.total_budget:
            scale_factor = self.total_budget / total_k
            print(f"[ROUTER] Scaling down k values by {scale_factor:.2f} to fit budget")
            
            for source_name in sources:
                original_k = sources[source_name].get("k", 0)
                sources[source_name]["k"] = max(0, int(original_k * scale_factor))
        
        # Ensure at least some retrieval happens
        total_k = sum(src.get("k", 0) for src in sources.values())
        if total_k == 0:
            print("[ROUTER] No retrieval planned, using fallback")
            return self._get_fallback_routing(query)
        
        return plan
    
    def _get_fallback_routing(self, query: Optional[str] = None) -> Dict:
        """
        Fallback routing when LLM fails.
        Returns balanced allocation across primary sources.
        Prioritizes internal sources over blog.
        """
        fallback = {
            "query_type": "general_info",
            "query_intent": "General query (fallback routing)",
            "sources": {
                "sharepoint": {"relevance": 0.7, "k": 20, "reasoning": "Fallback - SharePoint is primary internal documentation source"},
                "jira": {"relevance": 0.6, "k": 15, "reasoning": "Fallback - check for known issues and workarounds"},
                "pdfs": {"relevance": 0.5, "k": 10, "reasoning": "Fallback - technical documentation"},
                "blog": {"relevance": 0.2, "k": 2, "reasoning": "Fallback - low priority marketing content, use sparingly"},
                "transcripts": {"relevance": 0.0, "k": 0, "reasoning": "Fallback - skip transcripts"},
                "excel": {"relevance": 0.0, "k": 0, "reasoning": "Fallback - skip structured data"},
                "limitations": {"relevance": 0.0, "k": 0, "reasoning": "Fallback - only use when routing detects capabilities/support"}
            },
            "confidence": 0.4
        }
        
        # Exclude Jira for "who is" questions
        if query and self._is_who_is_question(query):
            fallback["sources"]["jira"]["k"] = 0
            fallback["sources"]["jira"]["relevance"] = 0.0
            fallback["sources"]["jira"]["reasoning"] = "Excluded - 'who is' questions don't need Jira tickets"
        
        return fallback
    
    def _log_routing_decision(self, query: str, plan: Dict):
        """Log routing decision for monitoring and debugging."""
        print("\n" + "="*70)
        print("[ROUTING] INTELLIGENT QUERY ROUTING")
        print("="*70)
        print(f"Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        print(f"Type: {plan.get('query_type', 'unknown')}")
        print(f"Intent: {plan.get('query_intent', 'unknown')}")
        print(f"Confidence: {plan.get('confidence', 0):.2f}")
        print("\n[ALLOCATION] Retrieval Allocation:")
        
        sources = plan.get("sources", {})
        total_k = 0
        
        for source_name, source_info in sorted(sources.items(), key=lambda x: x[1].get("k", 0), reverse=True):
            k = source_info.get("k", 0)
            relevance = source_info.get("relevance", 0)
            reasoning = source_info.get("reasoning", "")
            
            if k > 0:
                total_k += k
                bar = "=" * int(k / 2)  # Visual bar chart
                print(f"  {bar} {source_name:12} k={k:2d}  relevance={relevance:.2f}")
                print(f"     -> {reasoning}")
        
        print(f"\n[TOTAL] Documents: {total_k}/{self.total_budget}")
        print("="*70 + "\n")


def get_routing_confidence(plan: Dict) -> float:
    """
    Calculate overall confidence in routing decision.
    
    Args:
        plan: Routing plan from IntelligentQueryRouter
        
    Returns:
        Confidence score 0.0-1.0
    """
    llm_confidence = plan.get("confidence", 0.5)
    
    # Check if allocation makes sense
    sources = plan.get("sources", {})
    total_k = sum(src.get("k", 0) for src in sources.values())
    
    # Penalize if too few or too many sources allocated
    active_sources = sum(1 for src in sources.values() if src.get("k", 0) > 0)
    
    if active_sources == 0:
        return 0.0
    elif active_sources > 5:
        # Too many sources - might be uncertain
        llm_confidence *= 0.8
    
    # Penalize if total k is very low
    if total_k < 10:
        llm_confidence *= 0.7
    
    return min(llm_confidence, 1.0)
