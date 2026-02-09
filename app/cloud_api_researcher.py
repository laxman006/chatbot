# -*- coding: utf-8 -*-
"""
Cloud API Researcher Agent

Main research agent that orchestrates the complete cloud API research workflow:
1. Discovery Phase - Search for official documentation
2. Extraction Phase - Scrape and extract API details
3. Normalization Phase - Map to CloudFuze standard operations
4. Verification Phase - Validate URLs and detect SCIM

This creates comprehensive API blueprints for CloudFuze Manage integration.
"""

from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timezone

from app.web_tools import (
    search_cloud_documentation,
    scrape_documentation_pages,
    enterprise_surface_filter,
    search_cloud_documentation_capability_first,
    validate_admin_doc_candidates,
)
from app.api_normalizer import APIOperationNormalizer
from app.doc_link_extractor import extract_documentation_links
from app.openapi_parser import extract_endpoints_from_openapi
from app.endpoint_validator import validate_endpoints, validate_operation_mapping, EndpointValidator
from app.models.cloud_contract import calculate_coverage_score, get_all_operations
from app.models.cloud_research import save_cloud_research, get_cloud_research, is_research_cached
from config import (
    CLOUD_RESEARCH_WEB_SEARCH_API,
    CLOUD_RESEARCH_SEARCH_API_KEY,
    CLOUD_RESEARCH_MAX_URLS_PER_CLOUD,
    CLOUD_RESEARCH_CACHE_DAYS,
    CLOUD_RESEARCH_MIN_CONFIDENCE,
)

logger = logging.getLogger(__name__)


class CloudAPIResearcher:
    """Main agent for researching cloud APIs"""
    
    # Known documentation URLs for popular clouds (fallback when search fails)
    KNOWN_DOCS = {
        "slack": [
            {"url": "https://api.slack.com/methods", "title": "Slack API Methods"},
            {"url": "https://api.slack.com/scim", "title": "Slack SCIM API"},
            {"url": "https://api.slack.com/authentication", "title": "Slack Authentication"},
        ],
        "microsoft teams": [
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview", "title": "Microsoft Teams API Overview"},
            {"url": "https://learn.microsoft.com/en-us/graph/api/team-post", "title": "Microsoft Graph Teams API"},
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/user", "title": "Microsoft Graph Users"},
        ],
        "okta": [
            {"url": "https://developer.okta.com/docs/reference/api/users/", "title": "Okta Users API"},
            {"url": "https://developer.okta.com/docs/reference/api/groups/", "title": "Okta Groups API"},
            {"url": "https://developer.okta.com/docs/reference/scim/", "title": "Okta SCIM API"},
        ],
        "google workspace": [
            {"url": "https://developers.google.com/admin-sdk/directory/reference/rest", "title": "Google Admin SDK"},
            {"url": "https://developers.google.com/admin-sdk/directory/v1/guides/manage-users", "title": "Manage Users"},
            {"url": "https://developers.google.com/admin-sdk/directory/v1/guides/manage-groups", "title": "Manage Groups"},
        ],
        "aws": [
            {"url": "https://docs.aws.amazon.com/IAM/latest/UserGuide/id.html", "title": "AWS IAM Identities"},
            {"url": "https://docs.aws.amazon.com/IAM/latest/APIReference/API_Operations.html", "title": "AWS IAM API Reference"},
            {"url": "https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html", "title": "AWS IAM Identity Center"},
        ],
        "azure": [
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/azure-ad-overview", "title": "Azure AD Overview"},
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/user", "title": "Microsoft Graph Users"},
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/group", "title": "Microsoft Graph Groups"},
        ],
        "microsoft 365": [
            {"url": "https://learn.microsoft.com/en-us/graph/api/overview", "title": "Microsoft Graph API"},
            {"url": "https://learn.microsoft.com/en-us/graph/api/resources/user", "title": "User Resource"},
            {"url": "https://learn.microsoft.com/en-us/graph/auth/", "title": "Microsoft Graph Authentication"},
        ],
        "salesforce": [
            {"url": "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_rest.htm", "title": "Salesforce REST API"},
            {"url": "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_users.htm", "title": "User Management"},
            {"url": "https://help.salesforce.com/s/articleView?id=sf.identity_scim_overview.htm", "title": "Salesforce SCIM API"},
        ],
        "zoom": [
            {"url": "https://developers.zoom.us/docs/api/rest/reference/user/", "title": "Zoom User API"},
            {"url": "https://developers.zoom.us/docs/api/rest/reference/user/methods/", "title": "User Methods"},
            {"url": "https://developers.zoom.us/docs/integrations/oauth/", "title": "Zoom OAuth"},
        ],
        "dropbox": [
            {"url": "https://www.dropbox.com/developers/documentation/http/teams", "title": "Dropbox Team API"},
            {"url": "https://www.dropbox.com/developers/documentation/http/teams#team-members-list", "title": "Team Members"},
            {"url": "https://developers.dropbox.com/oauth-guide", "title": "Dropbox OAuth Guide"},
        ],
        "box": [
            {"url": "https://developer.box.com/reference/resources/user/", "title": "Box User API"},
            {"url": "https://developer.box.com/reference/resources/group/", "title": "Box Group API"},
            {"url": "https://developer.box.com/guides/authentication/", "title": "Box Authentication"},
        ],
        "github": [
            {"url": "https://docs.github.com/en/rest/users", "title": "GitHub Users API"},
            {"url": "https://docs.github.com/en/rest/orgs", "title": "GitHub Organizations API"},
            {"url": "https://docs.github.com/en/rest/teams", "title": "GitHub Teams API"},
        ],
        "atlassian": [
            {"url": "https://developer.atlassian.com/cloud/admin/user-management/rest/", "title": "Atlassian User Management API"},
            {"url": "https://developer.atlassian.com/cloud/admin/organization/rest/", "title": "Organization API"},
            {"url": "https://developer.atlassian.com/cloud/jira/platform/scim/", "title": "Atlassian SCIM"},
        ],
        "jira": [
            {"url": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/", "title": "Jira Cloud REST API"},
            {"url": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-users/", "title": "User Management"},
            {"url": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-groups/", "title": "Group Management"},
        ],
        "confluence": [
            {"url": "https://developer.atlassian.com/cloud/confluence/rest/v2/intro/", "title": "Confluence REST API"},
            {"url": "https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-user/", "title": "User API"},
            {"url": "https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-group/", "title": "Group API"},
        ],
        "vercel": [
            {"url": "https://vercel.com/docs/rest-api", "title": "Vercel REST API"},
            {"url": "https://vercel.com/docs/rest-api/reference/examples/team-management", "title": "Vercel Team Management (REST API)"},
            {"url": "https://vercel.com/docs/rest-api/reference/examples/logs-monitoring", "title": "Vercel Logs & Monitoring (REST API)"},
        ],
        "rollbar": [
            {"url": "https://docs.rollbar.com/reference/getting-started-1", "title": "Rollbar API Reference"},
            {"url": "https://docs.rollbar.com/reference/list-all-users", "title": "Rollbar Users API (GET /api/1/users)"},
            {"url": "https://docs.rollbar.com/reference/get-a-user", "title": "Rollbar Get User (GET /api/1/user/{id})"},
            {"url": "https://docs.rollbar.com/reference/list-all-teams", "title": "Rollbar Teams API (GET /api/1/teams)"},
            {"url": "https://docs.rollbar.com/reference/list-a-users-teams", "title": "Rollbar Teams (per user)"},
            {"url": "https://docs.rollbar.com/reference/list-a-teams-users", "title": "Rollbar Team Members (GET /api/1/team/{id}/users)"},
            {"url": "https://docs.rollbar.com/reference/assign-a-user-to-team", "title": "Rollbar Assign User to Team"},
        ],
        "mezmo": [
            {"url": "https://docs.mezmo.com/log-analysis-api/ref", "title": "Mezmo Log Analysis API"},
            {"url": "https://docs.mezmo.com/pipeline-api", "title": "Mezmo Pipeline API"},
        ],
    }
    
    def __init__(self, llm=None):
        """
        Initialize cloud API researcher.
        
        Args:
            llm: Language model for intelligent normalization
        """
        self.llm = llm
        self.normalizer = APIOperationNormalizer(llm)
    
    def _get_fallback_docs(self, cloud_name: str) -> List[Dict]:
        """
        Get documentation URLs using universal domain detection or known docs.
        
        Args:
            cloud_name: Name of the cloud
            
        Returns:
            List of documentation URLs
        """
        from app.domain_detector import UniversalDomainDetector
        
        detector = UniversalDomainDetector()
        
        # STRATEGY 1: Universal domain detection (works for ANY cloud)
        logger.info(f"[FALLBACK] Attempting universal domain detection for {cloud_name}")
        official_domain = detector.detect_official_domain(cloud_name)
        
        if official_domain:
            logger.info(f"[FALLBACK] ✓ Detected official domain: {official_domain}")
            doc_urls = detector.find_api_documentation_urls(official_domain, cloud_name)
            
            if doc_urls:
                logger.info(f"[FALLBACK] ✓ Found {len(doc_urls)} documentation URLs via domain detection")
                return [{"url": url, "title": f"{cloud_name} API Documentation", "snippet": ""} for url in doc_urls]
        
        # STRATEGY 2: Known docs (only for popular clouds as speed optimization)
        cloud_key = cloud_name.lower().strip()
        known_docs = self.KNOWN_DOCS.get(cloud_key, [])
        
        if known_docs:
            logger.info(f"[FALLBACK] Using {len(known_docs)} known docs for {cloud_name}")
            return [{"url": doc["url"], "title": doc["title"], "snippet": ""} for doc in known_docs]
        
        logger.warning(f"[FALLBACK] No fallback docs found for {cloud_name}")
        return []
    
    def _generate_docs_with_llm(self, cloud_name: str) -> List[Dict]:
        """
        Use LLM to generate likely documentation URLs for unknown clouds.
        
        Args:
            cloud_name: Name of the cloud
            
        Returns:
            List of generated documentation URLs
        """
        if not self.llm:
            logger.warning(f"[LLM FALLBACK] No LLM available for {cloud_name}")
            return []
        
        try:
            logger.info(f"[LLM FALLBACK] Generating documentation URLs for {cloud_name}")
            
            prompt = f"""You are a cloud API expert. Generate the most likely official documentation URLs for {cloud_name}'s REST API.

Requirements:
- Provide 3-5 URLs that are MOST LIKELY to be correct official documentation
- Focus on: User management API, Group/Team management API, Authentication/OAuth guide, SCIM API (if applicable)
- Use common patterns (developer.*, docs.*, api.*, learn.microsoft.com, etc.)
- Be specific and realistic

Format your response as JSON array:
[
  {{"url": "https://...", "title": "..."}},
  {{"url": "https://...", "title": "..."}}
]

Cloud: {cloud_name}

JSON (URLs only, no explanation):"""
            
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON from response
            import json
            import re
            
            # Try to find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                urls = json.loads(json_match.group(0))
                logger.info(f"[LLM FALLBACK] Generated {len(urls)} URLs for {cloud_name}")
                return [{"url": doc["url"], "title": doc["title"], "snippet": ""} for doc in urls]
            else:
                logger.warning(f"[LLM FALLBACK] Could not parse JSON from LLM response")
                return []
                
        except Exception as e:
            logger.error(f"[LLM FALLBACK] Failed to generate URLs: {e}")
            return []
    
    def research_cloud(
        self,
        cloud_name: str,
        user_email: str = "",
        force_refresh: bool = False
    ) -> Dict:
        """
        Perform complete research for a cloud provider.
        
        Args:
            cloud_name: Name of the cloud to research
            user_email: Email of user requesting research
            force_refresh: Force fresh research even if cached
            
        Returns:
            Complete research results dict
        """
        logger.info(f"[RESEARCH] Starting research for {cloud_name}")
        
        # Check cache
        if not force_refresh and is_research_cached(cloud_name, CLOUD_RESEARCH_CACHE_DAYS):
            logger.info(f"[CACHE HIT] Returning cached research for {cloud_name}")
            cached_result = get_cloud_research(cloud_name)
            if cached_result:
                cached_result["from_cache"] = True
                # Auto-refresh if cached result is low confidence or has no core ops
                confidence = cached_result.get("confidence_score", 0.0) or 0.0
                core_ops = cached_result.get("core_operations") or {}
                core_count = 0
                for category in core_ops.values():
                    if isinstance(category, list):
                        core_count += len(category)
                if confidence < CLOUD_RESEARCH_MIN_CONFIDENCE or core_count == 0:
                    logger.warning(
                        f"[CACHE BYPASS] Cached research for {cloud_name} is low quality "
                        f"(confidence={confidence:.2f}, core_ops={core_count}). Re-running research."
                    )
                else:
                    return cached_result
        
        # Phase 0: Classification (NEW - prevents hallucinations)
        logger.info(f"[PHASE 0] Classification - Categorizing {cloud_name}")
        from app.cloud_classifier import classify_cloud
        classification = classify_cloud(cloud_name)
        logger.info(f"[CLASSIFICATION] {cloud_name} → {classification['category']} (support: {classification['manage_team_support']})")
        
        # Phase 1: Discovery
        cloud_key = cloud_name.lower().strip()
        if cloud_key == "rollbar":
            # Rollbar: bypass web search; use only authoritative KNOWN_DOCS.
            logger.info("[PHASE 1] Discovery - Rollbar: using KNOWN_DOCS only (web search bypassed)")
            search_results = self._get_fallback_docs(cloud_name)
            if not search_results:
                logger.error("[ERROR] No KNOWN_DOCS for Rollbar")
                return {
                    "error": "No documentation found for Rollbar.",
                    "cloud_name": cloud_name,
                    "confidence_score": 0.0
                }
            logger.info(f"[DISCOVERY] Rollbar: using {len(search_results)} KNOWN_DOCS URLs")
        else:
            logger.info(f"[PHASE 1] Discovery - Searching for {cloud_name} documentation")
            search_results = self._discovery_phase(cloud_name)
            if not search_results:
                logger.warning(f"[WARNING] Web search returned no results for {cloud_name}")
                search_results = self._get_fallback_docs(cloud_name)
                if not search_results:
                    logger.info(f"[FALLBACK] No known URLs, trying LLM generation for {cloud_name}")
                    search_results = self._generate_docs_with_llm(cloud_name)
                if not search_results:
                    logger.error(f"[ERROR] No documentation found for {cloud_name} (all fallbacks failed)")
                    return {
                        "error": "No official documentation found. Please verify the cloud name and try again.",
                        "cloud_name": cloud_name,
                        "confidence_score": 0.0
                    }
                logger.info(f"[FALLBACK] Using {len(search_results)} fallback URLs for {cloud_name}")

        # Always merge in KNOWN_DOCS (official seeds) when available.
        # This does not add capabilities; it only ensures we actually scrape the
        # canonical official references for consistent evidence gathering.
        known = self.KNOWN_DOCS.get(cloud_key, [])
        if known:
            existing_urls = {r.get("url") for r in (search_results or []) if isinstance(r, dict)}
            merged = list(search_results or [])
            added = 0
            for doc in known:
                url = doc.get("url")
                if url and url not in existing_urls:
                    merged.append({"url": url, "title": doc.get("title", f"{cloud_name} API Documentation"), "snippet": ""})
                    existing_urls.add(url)
                    added += 1
            if added:
                logger.info(f"[DISCOVERY] Merged {added} KNOWN_DOCS URLs for {cloud_name}")
            search_results = merged

        # Enterprise Admin Doc Resolution (BEFORE scraping)
        # Produce a small set of high-confidence ADMIN/ENTERPRISE API doc URLs only.
        # Capability-first: find identity, team, membership, audit doc pages; filter by enterprise surface; validate before scrape.
        # Only validated admin doc URLs are scraped; if none, NOT_SUPPORTED is the correct outcome.
        admin_doc_results = self._enterprise_admin_doc_resolution_phase(cloud_name, search_results)
        if admin_doc_results:
            logger.info(f"[ENTERPRISE ADMIN DOC] Using {len(admin_doc_results)} validated admin doc URLs for scraping")
            search_results = admin_doc_results
        else:
            logger.info("[ENTERPRISE ADMIN DOC] No validated admin doc URLs; scraping 0 pages (NOT_SUPPORTED if no evidence)")
            search_results = []

        # Phase 2: Extraction
        logger.info(f"[PHASE 2] Extraction - Scraping {len(search_results)} pages")
        scraped_data = self._extraction_phase(search_results, cloud_name)
        
        # Phase 3: Normalization
        logger.info(f"[PHASE 3] Normalization - Mapping operations")
        normalized_data = self._normalization_phase(scraped_data, cloud_name)
        
        # Phase 4: Verification
        logger.info(f"[PHASE 4] Verification - Validating and organizing")
        # Collect authoritative documentation URLs (informational only, does not affect integration_mode)
        authoritative_docs = []
        # Include validated admin doc URLs from Enterprise Admin Doc Resolution
        if admin_doc_results:
            authoritative_docs.extend([r.get("url") for r in admin_doc_results if isinstance(r, dict) and r.get("url")])
        # Include KNOWN_DOCS URLs (official references)
        known_docs = self.KNOWN_DOCS.get(cloud_key, [])
        if known_docs:
            authoritative_docs.extend([doc.get("url") for doc in known_docs if doc.get("url")])
        # Deduplicate
        authoritative_docs = list(dict.fromkeys(authoritative_docs))  # Preserves order, removes duplicates
        # Optional doc crawl: only when authoritative_docs is empty (UX improvement; does not affect integration_mode or confidence)
        if not authoritative_docs:
            try:
                from app.domain_detector import UniversalDomainDetector
                from app.web_tools import crawl_documentation_urls_only
                detector = UniversalDomainDetector()
                official_domain = detector.detect_official_domain(cloud_name)
                if official_domain:
                    seed_urls = detector.find_api_documentation_urls(official_domain, cloud_name)
                    if seed_urls:
                        logger.info("[DOC CRAWL] authoritative_docs empty; running URL-only documentation crawl")
                        crawled = crawl_documentation_urls_only(seed_urls, official_domain, max_depth=2)
                        if crawled:
                            authoritative_docs = list(dict.fromkeys(crawled))
                            logger.info(f"[DOC CRAWL] Populated authoritative_docs with {len(authoritative_docs)} URLs")
                    else:
                        logger.info("[DOC CRAWL] authoritative_docs empty; no seed URLs, crawl skipped")
                else:
                    logger.info("[DOC CRAWL] authoritative_docs empty; no official domain, crawl skipped")
            except Exception as e:
                logger.warning(f"[DOC CRAWL] Crawl skipped (non-fatal): {e}")
        else:
            logger.info("[DOC CRAWL] authoritative_docs non-empty; crawl skipped")
        final_data = self._verification_phase(cloud_name, normalized_data, scraped_data, classification, authoritative_docs)
        
        # Add metadata
        final_data.update({
            "cloud_name": cloud_name,
            "display_name": cloud_name,
            "created_by": user_email or "system",
            "last_researched": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
        })
        
        # Save to database
        save_cloud_research(final_data)
        
        logger.info(f"[COMPLETE] Research complete for {cloud_name} (confidence: {final_data.get('confidence_score', 0):.2f})")
        return final_data
    
    def _llm_extraction_fallback_DISABLED(self, cloud_name: str, urls: List[str], scraped_pages: List[Dict]) -> List[Dict]:
        """
        DISABLED: LLM-powered extraction caused hallucinations.
        Replaced with JavaScript rendering (Playwright) for accurate extraction.
        
        This method is kept for reference but should NOT be used.
        
        Args:
            cloud_name: Name of the cloud
            urls: Documentation URLs that were scraped
            scraped_pages: Pages that were scraped (with 0 endpoints)
            
        Returns:
            List of endpoint dictionaries
        """
        if not self.llm:
            return []
        
        try:
            # Get text content from scraped pages
            docs_context = ""
            for page in scraped_pages[:2]:  # Use first 2 pages
                content = page.get('content', '')
                if content:
                    docs_context += f"\n\n=== {page.get('title', 'Documentation')} ===\n{content[:3000]}"  # Limit content
            
            if not docs_context.strip():
                docs_context = f"Documentation URL: {urls[0] if urls else 'unknown'}"
            
            logger.info(f"[LLM EXTRACTION] Using LLM to extract endpoints for {cloud_name}")
            
            prompt = f"""You are an expert at analyzing API documentation. The HTML scraping failed to extract endpoints from {cloud_name}'s API documentation (likely JavaScript-rendered).

Based on the documentation context and your knowledge of {cloud_name}'s API, extract the ESSENTIAL USER AND GROUP MANAGEMENT endpoints.

**FOCUS ON THESE 8 OPERATIONS ONLY:**
1. getUsers - List/get all users (GET /users, GET /api/users/list, etc.)
2. getAdmins - List admin users  
3. createUser - Create a new user (POST /users, POST /api/users/create, etc.)
4. deleteUser - Delete a user (DELETE /users/{{id}}, POST /api/users/delete, etc.)
5. getGroups - List/get all groups (GET /groups, GET /api/groups/list, etc.)
6. getGroupMembers - Get members of a group (GET /groups/{{id}}/members, etc.)
7. addUserToGroup - Add user to group (POST /groups/{{id}}/members, PUT /groups/{{gid}}/users/{{uid}}, etc.)
8. removeUserFromGroup - Remove user from group (DELETE /groups/{{id}}/members/{{uid}}, etc.)

**Documentation Context:**
{docs_context[:2000]}

**Instructions:**
- Extract ONLY endpoints for the 8 operations listed above
- Use actual paths from {cloud_name}'s documentation if known
- If not in context, use your knowledge of {cloud_name}'s actual API
- Include HTTP method (GET, POST, DELETE, etc.)
- Be accurate - only include endpoints that {cloud_name} actually provides

**Return ONLY valid JSON array, no explanations:**
[
  {{
    "method": "GET",
    "path": "/api/v2/users/list",
    "description": "List all users",
    "operation_name": "getUsers"
  }},
  {{
    "method": "POST",
    "path": "/api/v1/users/create",
    "description": "Create a new user",
    "operation_name": "createUser"
  }}
]

Cloud: {cloud_name}
JSON Array:"""
            
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON from response
            import json
            import re
            
            # Try to find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                endpoints_json = json.loads(json_match.group(0))
                
                if isinstance(endpoints_json, list) and len(endpoints_json) > 0:
                    logger.info(f"[LLM EXTRACTION] Successfully extracted {len(endpoints_json)} endpoints")
                    return endpoints_json
            
            logger.warning(f"[LLM EXTRACTION] Failed to parse LLM response")
            return []
            
        except Exception as e:
            logger.error(f"[LLM EXTRACTION] Error: {e}")
            import traceback
            logger.error(f"[LLM EXTRACTION] Traceback: {traceback.format_exc()}")
            return []
    
    def _discovery_phase(self, cloud_name: str) -> List[Dict]:
        """
        Phase 1: Discover official API documentation.
        
        Args:
            cloud_name: Name of the cloud
            
        Returns:
            List of search results with URLs to scrape
        """
        try:
            results = search_cloud_documentation(
                cloud_name,
                search_api=CLOUD_RESEARCH_WEB_SEARCH_API,
                api_key=CLOUD_RESEARCH_SEARCH_API_KEY
            )
            
            logger.info(f"[DISCOVERY] Found {len(results)} official documentation sources")
            return results[:CLOUD_RESEARCH_MAX_URLS_PER_CLOUD]
            
        except Exception as e:
            logger.error(f"[ERROR] Discovery phase failed: {e}")
            return []

    def _enterprise_admin_doc_resolution_phase(self, cloud_name: str, search_results: List[Dict]) -> List[Dict]:
        """
        Enterprise Admin Doc Resolution (BEFORE scraping).
        Produce a small set of high-confidence ADMIN/ENTERPRISE API documentation URLs
        for identity, team, membership, and audit. Capability-first discovery; strict
        enterprise surface filtering; domain validation; validate doc pages before scraping.
        """
        from urllib.parse import urlparse
        try:
            cloud_key = cloud_name.lower().strip()
            candidates = list(search_results or [])
            if not isinstance(candidates, list):
                candidates = []

            try:
                from app.domain_detector import UniversalDomainDetector
                detector = UniversalDomainDetector()
                official_domain = detector.detect_official_domain(cloud_name)
            except Exception:
                official_domain = None

            # For non-Rollbar: add capability-first search results (find doc PAGES, not endpoints).
            if cloud_key != "rollbar" and official_domain:
                cap_results = search_cloud_documentation_capability_first(
                    cloud_name,
                    search_api=CLOUD_RESEARCH_WEB_SEARCH_API,
                    api_key=CLOUD_RESEARCH_SEARCH_API_KEY,
                    official_domain=official_domain,
                )
                seen = {r.get("url") for r in candidates if isinstance(r, dict) and r.get("url")}
                for r in cap_results:
                    if isinstance(r, dict) and r.get("url") and r["url"] not in seen:
                        seen.add(r["url"])
                        candidates.append(r)
                if cap_results:
                    logger.info(f"[ENTERPRISE ADMIN DOC] Capability-first search added {len(cap_results)} candidate URLs")

            # Domain validation: keep only URLs from official domain (or subdomain). LLM-suggested URLs must pass this.
            # Explicit normalization: www.dropbox.com and dropbox.com are the same (admin docs under www.dropbox.com/developers/ are valid).
            if official_domain:
                domain_normalized = official_domain.lower().replace("www.", "")
                domain_valid = []
                for r in candidates:
                    url = (r.get("url") or "").strip()
                    if not url:
                        continue
                    try:
                        netloc_raw = urlparse(url).netloc.lower()
                        netloc = netloc_raw.replace("www.", "")
                        if netloc == domain_normalized or netloc.endswith("." + domain_normalized):
                            domain_valid.append(r)
                    except Exception:
                        continue
                if domain_valid != candidates:
                    logger.info(f"[ENTERPRISE ADMIN DOC] Domain validation: {len(domain_valid)} URLs on {official_domain} (from {len(candidates)} candidates)")
                candidates = domain_valid
                if not candidates:
                    return []

            # Strict enterprise surface filter: keep only URLs containing admin/team/enterprise/reference/api/ etc.
            filtered = enterprise_surface_filter(candidates)
            logger.info(f"[ENTERPRISE ADMIN DOC] After enterprise surface filter: {len(filtered)} URLs (from {len(candidates)} candidates)")
            if not filtered:
                return []

            # Validate doc pages BEFORE scraping: title + content checks; exclude marketing/blog/SDK/UI.
            validated = validate_admin_doc_candidates(filtered, max_validate=15)
            logger.info(f"[ENTERPRISE ADMIN DOC] After pre-scrape validation: {len(validated)} scrapable admin doc URLs")
            return validated

        except Exception as e:
            logger.error(f"[ERROR] Enterprise Admin Doc Resolution failed: {e}")
            return []

    def _extraction_phase(self, search_results: List[Dict], cloud_name: str = "") -> List[Dict]:
        """
        Phase 2: Extract API details from documentation pages.
        
        Strategy (CRITICAL for modern APIs):
        1. First try OpenAPI/Swagger spec parsing (PRIMARY - works for 90% of modern APIs)
        2. Fall back to HTML scraping only if OpenAPI not found
        
        Args:
            search_results: List of URLs to scrape
            cloud_name: Name of cloud (for known OpenAPI specs)
            
        Returns:
            List of scraped page data with endpoints
        """
        try:
            urls = [result["url"] for result in search_results]
            
            # STRATEGY 1: OpenAPI spec parsing (PRIMARY METHOD)
            logger.info(f"[EXTRACTION] Step 1: Attempting OpenAPI/Swagger spec parsing for {cloud_name or 'unknown cloud'}")
            openapi_endpoints: List[Dict] = []
            openapi_base_url: Optional[str] = None
            openapi_spec_url: Optional[str] = None
            try:
                from app.openapi_parser import OpenAPIParser
                parser = OpenAPIParser()
                spec_urls = parser.find_openapi_specs_in_docs(urls, cloud_name)
                for spec_url in spec_urls:
                    spec_data = parser.parse_spec(spec_url)
                    if not spec_data:
                        continue
                    openapi_spec_url = spec_url
                    openapi_base_url = openapi_base_url or spec_data.get("base_url")
                    openapi_endpoints.extend(spec_data.get("endpoints", []) or [])
            except Exception as e:
                logger.warning(f"[EXTRACTION] OpenAPI parsing failed: {e}")

            if openapi_endpoints:
                logger.info(f"[EXTRACTION] ✅ OpenAPI extraction SUCCESSFUL: {len(openapi_endpoints)} endpoints")
                return [{
                    "url": openapi_spec_url or (urls[0] if urls else "openapi_spec"),
                    "title": "OpenAPI/Swagger Specification",
                    "api_endpoints": openapi_endpoints,
                    "content": f"Extracted {len(openapi_endpoints)} endpoints from OpenAPI/Swagger specification",
                    "source": "openapi",
                    "base_url": openapi_base_url,
                    "code_examples": [],
                    "links": []
                }]
            
            # STRATEGY 2: HTML scraping (FALLBACK)
            logger.info(f"[EXTRACTION] Step 2: HTML scraping {min(len(urls), CLOUD_RESEARCH_MAX_URLS_PER_CLOUD)} pages")
            scraped_pages = scrape_documentation_pages(urls, max_pages=CLOUD_RESEARCH_MAX_URLS_PER_CLOUD)
            
            # Merge OpenAPI endpoints with HTML scraped data
            if openapi_endpoints and scraped_pages:
                logger.info(f"[EXTRACTION] Merging OpenAPI + HTML: {len(openapi_endpoints)} + {sum(len(p.get('api_endpoints', [])) for p in scraped_pages)} endpoints")
                # Add OpenAPI endpoints to first page
                if scraped_pages:
                    existing = scraped_pages[0].get('api_endpoints', [])
                    scraped_pages[0]['api_endpoints'] = existing + openapi_endpoints
            
            # Skip early return - we'll use JS rendering instead
            # if not scraped_pages:
            #     logger.error("[EXTRACTION] No data extracted from HTML or OpenAPI")
            #     return []
            
            total_endpoints = sum(len(page.get('api_endpoints', [])) for page in scraped_pages) if scraped_pages else 0
            if scraped_pages:
                logger.info(f"[EXTRACTION] Successfully extracted {total_endpoints} total endpoints from {len(scraped_pages)} sources")
            else:
                logger.info(f"[EXTRACTION] Skipped HTML scraping - proceeding directly to JavaScript rendering")
            
            # STRATEGY 3: JavaScript rendering (PRIMARY for JS-rendered sites like Box)
            # Since HTML scraping is skipped, always use JS rendering
            # Activate if:
            # 1. We found 0 endpoints (obvious JS rendering needed), OR
            # 2. We found endpoints but they're not user/group management (wrong section), OR
            # 3. HTML scraping was skipped (empty scraped_pages)
            
            should_try_js = False
            
            if not scraped_pages or total_endpoints == 0:
                logger.info(f"[EXTRACTION] HTML scraping skipped or 0 endpoints - using JavaScript rendering")
                should_try_js = True
            else:
                # Quick check: do we have any identity/team-management endpoints?
                # Do NOT treat query parameters like `teamId` as evidence of team-management APIs.
                manage_path_indicators = [
                    "/users", "/user", "/groups", "/group", "/teams", "/team",
                    "/members", "/member",
                    "/audit", "/logs", "/activity",
                    "/oauth", "/token", "/auth",
                ]
                found_relevant = False
                
                for page in scraped_pages:
                    for endpoint in page.get('api_endpoints', []):
                        path = (endpoint.get('path', '') or '').lower()
                        path = path.split('?', 1)[0].split('#', 1)[0]
                        if any(indicator in path for indicator in manage_path_indicators):
                            found_relevant = True
                            break
                    if found_relevant:
                        break
                
                if not found_relevant:
                    logger.warning(f"[EXTRACTION] Extracted {total_endpoints} endpoints but NONE are user/group management related")
                    logger.info(f"[EXTRACTION] Endpoints found: {[ep.get('path', '') for page in scraped_pages for ep in page.get('api_endpoints', [])[:3]]}")
                    should_try_js = True
            
            if should_try_js and urls:
                logger.info(f"[EXTRACTION] Step 3: Attempting JavaScript rendering for {cloud_name}")
                
                try:
                    from app.js_scraper import scrape_with_javascript
                    
                    # ENHANCED: Prioritize URLs by importance for better extraction
                    # Priority 1: Authentication/OAuth pages (critical for integration)
                    auth_urls = []
                    # Priority 2: DELETE operations (often missed)
                    delete_urls = []
                    # Priority 3: User/Group management pages
                    user_group_urls = []
                    # Priority 4: Other pages
                    other_urls = []
                    
                    auth_keywords = ['auth', 'oauth', 'token', 'authentication', 'authorization']
                    delete_keywords = ['delete', 'remove', 'destroy']
                    user_group_keywords = ['user', 'group', 'team', 'member', 'admin', 'account', 'membership']
                    
                    for url in urls:
                        url_lower = url.lower()
                        
                        # Check authentication pages first
                        if any(keyword in url_lower for keyword in auth_keywords):
                            auth_urls.append(url)
                        # Then DELETE operations
                        elif any(keyword in url_lower for keyword in delete_keywords):
                            delete_urls.append(url)
                        # Then user/group management
                        elif any(keyword in url_lower for keyword in user_group_keywords):
                            user_group_urls.append(url)
                        # Everything else
                        else:
                            other_urls.append(url)
                    
                    # Combine: auth first, delete second, user/group third, then others
                    # If no auth/user/group pages exist, include more "other" pages for coverage
                    other_limit = 5 if (not auth_urls and not user_group_urls and not delete_urls) else 1
                    urls_to_scrape = auth_urls + delete_urls + user_group_urls[:3] + other_urls[:other_limit]
                    
                    # Scrape up to 8 pages with endpoints when coverage is poor
                    max_js_pages = min(8, len(urls_to_scrape))
                    logger.info(f"[EXTRACTION] Scraping up to {max_js_pages} useful pages with JavaScript (speed-optimized)")
                    logger.info(f"[EXTRACTION] URL Priority: {len(auth_urls)} auth, {len(delete_urls)} delete, {len(user_group_urls[:3])} user/group (top 3), {len(other_urls[:1])} other")
                    
                    js_results = scrape_with_javascript(urls_to_scrape, max_pages=max_js_pages, cloud_name=cloud_name)
                    
                    if js_results:
                        js_endpoints_count = sum(len(page.get('api_endpoints', [])) for page in js_results)
                        logger.info(f"[EXTRACTION] ✅ JavaScript rendering found {js_endpoints_count} endpoints")
                        
                        if js_endpoints_count > 0:
                            # Replace scraped_pages with JS results
                            scraped_pages = js_results
                            total_endpoints = js_endpoints_count
                        else:
                            logger.warning(f"[EXTRACTION] JavaScript rendering also found 0 endpoints")
                    
                except Exception as e:
                    logger.error(f"[EXTRACTION] JavaScript rendering failed: {e}")
                    import traceback
                    logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")
                    # Continue with original scraped_pages
            
            return scraped_pages
            
        except Exception as e:
            logger.error(f"[ERROR] Extraction phase failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _normalization_phase(self, scraped_data: List[Dict], cloud_name: str = "") -> Dict:
        """
        Phase 3: Normalize extracted APIs to CloudFuze standard WITH VALIDATION.
        
        Process:
        1. Collect endpoints
        2. Validate endpoints (semantic checks)
        3. Map to CloudFuze operations
        4. Validate mappings (semantic correctness)
        5. Return validated results
        
        Args:
            scraped_data: List of scraped page data
            
        Returns:
            Dict with normalized and validated operations
        """
        try:
            # STEP 1: Collect all endpoints from all pages
            all_endpoints = []
            for page in scraped_data:
                endpoints = page.get("api_endpoints", [])
                for ep in endpoints:
                    # Keep all original fields + add normalized fields for compatibility
                    # Don't remap - keep "path" as "path", "operation_name" as "operation_name"
                    endpoint_data = {
                        "method": ep.get("method", ""),
                        "path": ep.get("path", ep.get("endpoint", "")),  # Support both field names
                        "operation_name": ep.get("operation_name", ep.get("vendor_operation", "")),
                        "description": ep.get("description", ""),
                        "source_url": page.get("url", ""),
                        "page_source": page.get("source", ""),
                        "evidence_source": ep.get("source", ""),
                        "category": ep.get("category", "other"),
                        # Legacy field names for backward compatibility
                        "vendor_operation": ep.get("operation_name", ep.get("vendor_operation", "")),
                        "endpoint": ep.get("path", ep.get("endpoint", ""))
                    }
                    all_endpoints.append(endpoint_data)
            
            logger.info(f"[NORMALIZE] Processing {len(all_endpoints)} endpoints")
            
            # STEP 2: Validate endpoints (reject semantically invalid ones)
            validator = EndpointValidator()
            validated_endpoints = []
            rejected_endpoints = []
            
            for ep in all_endpoints:
                is_valid, reason, penalty = validator.validate_endpoint(ep)
                if is_valid:
                    validated_endpoints.append(ep)
                else:
                    rejected_endpoints.append({"endpoint": ep, "reason": reason})
                    # Use .get() for safety since field names vary by source
                    path = ep.get('path', ep.get('endpoint', 'N/A'))
                    logger.info(f"[VALIDATION] Rejected: {ep['method']} {path} - {reason}")
            
            logger.info(f"[VALIDATION] {len(validated_endpoints)}/{len(all_endpoints)} endpoints passed validation")
            
            # STEP 3: Normalize validated endpoints to CloudFuze operations
            core_operations = {}
            extended_operations = {}
            unmapped_operations = []
            invalid_mappings = []
            
            for ep in validated_endpoints:
                # Try to map to CloudFuze operation
                # Handle field name variations: OpenAPI uses 'path'/'operation_name', HTML scraper uses 'endpoint'/'vendor_operation'
                vendor_op = ep.get("operation_name", ep.get("vendor_operation", ""))
                endpoint_path = ep.get("path", ep.get("endpoint", ""))
                
                cloudfuze_op, confidence = self.normalizer.normalize_operation(
                    vendor_operation=vendor_op,
                    endpoint=endpoint_path,
                    method=ep["method"],
                    description=ep.get("description", "")
                )
                
                if cloudfuze_op and confidence >= CLOUD_RESEARCH_MIN_CONFIDENCE:
                    # STEP 4: Validate the mapping is semantically correct
                    is_valid_mapping, validation_reason, adjusted_confidence = validate_operation_mapping(
                        ep, cloudfuze_op, confidence
                    )
                    
                    if not is_valid_mapping:
                        ep_path = ep.get('path', ep.get('endpoint', 'N/A'))
                        logger.warning(f"[VALIDATION] Rejected mapping: {ep['method']} {ep_path} → {cloudfuze_op}: {validation_reason}")
                        invalid_mappings.append({
                            "endpoint": ep,
                            "attempted_operation": cloudfuze_op,
                            "reason": validation_reason
                        })
                        unmapped_operations.append(ep)
                        continue
                    
                    # Determine if core or extended
                    contract = get_all_operations()
                    is_core = False
                    
                    for category in contract["core_operations"].values():
                        if cloudfuze_op in category:
                            is_core = True
                            break
                    
                    operation_data = {
                        "cloudfuze_operation": cloudfuze_op,
                        "vendor_operation": vendor_op or endpoint_path,
                        "method": ep["method"],
                        "endpoint": endpoint_path,
                        "description": ep.get("description", ""),
                        "vendor_docs_url": ep.get("source_url", ""),
                        "page_source": ep.get("page_source", ""),
                        "evidence_source": ep.get("evidence_source", ""),
                        "normalization_confidence": adjusted_confidence,
                        "validation_status": "validated"
                    }
                    
                    if is_core:
                        if cloudfuze_op not in core_operations:
                            core_operations[cloudfuze_op] = []
                        core_operations[cloudfuze_op].append(operation_data)
                    else:
                        if cloudfuze_op not in extended_operations:
                            extended_operations[cloudfuze_op] = []
                        extended_operations[cloudfuze_op].append(operation_data)
                else:
                    unmapped_operations.append(ep)
            
            logger.info(f"[NORMALIZE] Mapped {len(core_operations)} core + {len(extended_operations)} extended operations")
            logger.info(f"[VALIDATION] Rejected {len(invalid_mappings)} semantically invalid mappings")
            logger.info(f"[VALIDATION] {len(rejected_endpoints)} endpoints failed validation")
            
            return {
                "core_operations": core_operations,
                "extended_operations": extended_operations,
                "unmapped_operations": unmapped_operations,
                "invalid_mappings": invalid_mappings,
                "rejected_endpoints": rejected_endpoints,
                "total_endpoints_found": len(all_endpoints),
                "validated_endpoints": len(validated_endpoints)
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Normalization phase failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "core_operations": {},
                "extended_operations": {},
                "unmapped_operations": [],
                "invalid_mappings": [],
                "rejected_endpoints": [],
                "total_endpoints_found": 0,
                "validated_endpoints": 0
            }
    
    def _verification_phase(self, cloud_name: str, normalized_data: Dict, scraped_data: List[Dict], classification: Dict, authoritative_docs: List[str] = None) -> Dict:
        """
        Phase 4: Verify data, extract documentation links, detect SCIM.
        
        Args:
            cloud_name: Name of the cloud
            normalized_data: Normalized operation data
            scraped_data: Raw scraped data
            classification: Cloud classification data
            
        Returns:
            Final verified and organized research data
        """
        try:
            # Extract documentation links
            doc_links = extract_documentation_links(scraped_data, cloud_name)
            
            # SCIM is HARD BLOCKED - always return disabled
            from config import ALLOW_SCIM
            if ALLOW_SCIM:
                scim_support = self._detect_scim_support(scraped_data, doc_links)
            else:
                scim_support = {"supported": False, "version": None, "endpoints": []}
            
            # Calculate coverage score (cloud-type aware expectations)
            from app.cloud_classifier import get_expected_operations_for_cloud
            expected_ops = get_expected_operations_for_cloud(classification)
            supported_ops = list(normalized_data.get("core_operations", {}).keys())
            coverage = calculate_coverage_score(supported_ops, expected_ops)
            
            # Calculate confidence score (with cloud-type caps)
            confidence = self._calculate_confidence_score(normalized_data, scraped_data, classification)
            
            # Extract base URL and authentication details from scraped data
            base_url = self._extract_base_url_from_scraped(scraped_data, cloud_name)
            auth_details = self._extract_auth_details_from_scraped(scraped_data, cloud_name)
            all_endpoints = self._extract_all_endpoints_from_scraped(scraped_data, normalized_data)

            integration_mode = self._compute_integration_mode(
                core_operations=normalized_data.get("core_operations", {}),
                extended_operations=normalized_data.get("extended_operations", {}),
            )
            
            # Organize final data
            final_data = {
                "cloud_classification": classification,  # NEW: Include classification
                "integration_mode": integration_mode,
                "base_url": base_url,  # NEW: Base URL for API integration
                "authentication": auth_details,  # NEW: Full authentication details
                "all_endpoints": all_endpoints,  # NEW: All discovered endpoints (not just mapped)
                "api_version": self._detect_api_version(scraped_data),
                "documentation": doc_links,
                "scim_support": scim_support,
                "core_operations": normalized_data.get("core_operations", {}),
                "extended_operations": normalized_data.get("extended_operations", {}),
                "unmapped_operations_count": len(normalized_data.get("unmapped_operations", [])),
                "all_available_endpoints": {
                    "total_count": normalized_data.get("total_endpoints_found", 0),
                    "core_count": len(normalized_data.get("core_operations", {})),
                    "extended_count": len(normalized_data.get("extended_operations", {})),
                },
                "coverage_metrics": coverage,
                "confidence_score": confidence,
                "research_notes": self._generate_research_notes(normalized_data, scim_support, classification),
                "source_urls": [page.get("url") for page in scraped_data],
                "authoritative_docs": authoritative_docs or [],  # Informational only; does not affect integration_mode
            }
            source_urls = final_data["source_urls"]
            cloud_key = cloud_name.lower().strip()
            if cloud_key in ("rollbar", "mezmo"):
                logger.info(f"[EVIDENCE] {cloud_name}: integration_mode={integration_mode}, {len(all_endpoints)} endpoints from {len(source_urls)} source URLs")
                logger.debug(f"[EVIDENCE] {cloud_name}: source_urls={source_urls}")
                for ep in all_endpoints:
                    logger.debug(f"[EVIDENCE] {cloud_name}: endpoint {ep.get('method', '')} {ep.get('path', '')} <- {ep.get('vendor_docs_url', '')}")
            
            logger.info(f"[VERIFICATION] Verification complete")
            return final_data
            
        except Exception as e:
            logger.error(f"[ERROR] Verification phase failed: {e}")
            return {
                "error": "Verification failed",
                "confidence_score": 0.0
            }

    def _compute_integration_mode(self, core_operations: Dict, extended_operations: Dict) -> str:
        """
        Compute integration mode per docs/integration-modes.md.
        Capability-first: derived only from explicitly evidenced operations.

        GUARDRAILS (do not relax):
        - Integration mode is strictly evidence-driven; no inference or heuristic upgrades.
        - Admin API documentation is the only source of truth for capabilities.
        - Do not add fallbacks, retries, or heuristics that change mode based on cloud name or assumptions.
        """
        user_ops = {"getUsers", "getUser", "createUser", "updateUser", "deleteUser", "suspendUser", "restoreUser"}
        group_ops = {"getGroups", "getGroup", "createGroup", "updateGroup", "deleteGroup"}
        membership_ops = {"getGroupMembers", "addUserToGroup", "removeUserFromGroup"}

        has_any_user = any(op in core_operations for op in user_ops)
        has_any_group = any(op in core_operations for op in group_ops)
        has_any_membership = any(op in core_operations for op in membership_ops)

        has_user_lifecycle = any(op in core_operations for op in {"createUser", "updateUser", "deleteUser", "suspendUser", "restoreUser"})
        has_group_lifecycle = any(op in core_operations for op in {"createGroup", "updateGroup", "deleteGroup"})
        has_membership_writes = any(op in core_operations for op in {"addUserToGroup", "removeUserFromGroup"})

        has_audit = any(op in extended_operations for op in {"getAuditLogs", "getSecurityEvents"})

        # Validate integration modes per required rules:
        # - FULL_IDENTITY_GOVERNANCE only if explicit user + group lifecycle endpoints exist
        # - PARTIAL_GOVERNANCE only if explicit team/membership OR audit endpoints exist
        # - VISIBILITY_ONLY only if read-only discovery or audit endpoints exist
        # - NOT_SUPPORTED otherwise

        has_any_identity_or_team = has_any_user or has_any_group or has_any_membership
        has_any_write = has_user_lifecycle or has_group_lifecycle or has_membership_writes
        has_any_read = (
            any(op in core_operations for op in {"getUsers", "getUser"}) or
            any(op in core_operations for op in {"getGroups", "getGroup"}) or
            ("getGroupMembers" in core_operations)
        )

        if has_user_lifecycle and has_group_lifecycle:
            return "FULL_IDENTITY_GOVERNANCE"

        has_team_or_membership = has_any_group or has_any_membership
        if has_team_or_membership or has_audit:
            # If this is only read-only discovery/audit, classify VISIBILITY_ONLY
            if (has_any_read or has_audit) and not has_any_write:
                return "VISIBILITY_ONLY"
            return "PARTIAL_GOVERNANCE"

        if (has_any_read or has_audit) and not has_any_write:
            return "VISIBILITY_ONLY"

        return "NOT_SUPPORTED"
    
    def _extract_base_url_from_scraped(self, scraped_data: List[Dict], cloud_name: str = "") -> Optional[str]:
        """
        Extract base URL from scraped pages.
        Returns the most common base URL found, rejecting placeholders.
        """
        base_urls = []
        for page in scraped_data:
            base_url = page.get("base_url")
            if base_url:
                base_urls.append(base_url)
        
        if not base_urls:
            return None
        
        # Get most common base URL
        from collections import Counter
        most_common = Counter(base_urls).most_common(1)
        extracted_url = most_common[0][0] if most_common else None
        
        if not extracted_url:
            return None
        
        # Reject placeholder URLs like example.com
        if any(placeholder in extracted_url.lower() for placeholder in ['example.com', 'yoursite.com', 'sample.com', 'placeholder', 'your-domain']):
            logger.warning(f"[BASE URL] Detected placeholder URL: {extracted_url} (rejected)")
            return None
        
        return extracted_url
    
    def _extract_auth_details_from_scraped(self, scraped_data: List[Dict], cloud_name: str = "") -> Dict:
        """
        Extract authentication details from scraped pages.
        Aggregates OAuth endpoints, scopes, and auth type with LLM validation.
        
        Args:
            scraped_data: List of scraped page data
            cloud_name: Name of cloud for LLM context
            
        Returns:
            Aggregated and validated authentication details
        """
        auth_details = {
            "type": "Unknown",
            "token_endpoint": None,
            "authorization_endpoint": None,
            "scopes": [],
            "admin_consent_required": False,
            "grant_types": []
        }
        
        for page in scraped_data:
            page_auth = page.get("authentication", {})
            if not page_auth:
                continue
            
            # Get auth type
            if page_auth.get("auth_type") and auth_details["type"] == "Unknown":
                auth_details["type"] = page_auth.get("auth_type")
            
            # Get OAuth endpoints
            if page_auth.get("token_endpoint") and not auth_details["token_endpoint"]:
                auth_details["token_endpoint"] = page_auth.get("token_endpoint")
            
            if page_auth.get("authorization_endpoint") and not auth_details["authorization_endpoint"]:
                auth_details["authorization_endpoint"] = page_auth.get("authorization_endpoint")
            
            # Aggregate scopes
            if page_auth.get("scopes"):
                auth_details["scopes"].extend(page_auth.get("scopes", []))
            
            # Check admin consent
            if page_auth.get("admin_consent_required"):
                auth_details["admin_consent_required"] = True
        
        # Deduplicate scopes
        auth_details["scopes"] = list(set(auth_details["scopes"]))
        
        # No LLM validation: scopes are evidence-only; if ambiguous, keep empty.
        
        # Infer grant types based on endpoints
        if auth_details["authorization_endpoint"]:
            auth_details["grant_types"].append("authorization_code")
        if auth_details["token_endpoint"]:
            auth_details["grant_types"].append("client_credentials")
        
        return auth_details
    
    def _extract_all_endpoints_from_scraped(self, scraped_data: List[Dict], normalized_data: Dict) -> List[Dict]:
        """
        Extract ALL discovered endpoints from scraped pages (not just mapped ones).
        Returns comprehensive list for integration reference.
        """
        all_endpoints = []
        seen_endpoints = set()
        
        for page in scraped_data:
            endpoints = page.get("api_endpoints", [])
            for ep in endpoints:
                method = ep.get("method", "")
                path = ep.get("path", "")
                key = f"{method}:{path}"
                
                if key not in seen_endpoints:
                    seen_endpoints.add(key)
                    all_endpoints.append({
                        "method": method,
                        "path": path,
                        "description": ep.get("description", ""),
                        "operation_name": ep.get("operation_name", ""),
                        "source": ep.get("source", ""),
                        "vendor_docs_url": page.get("url", "")
                    })
        
        # Sort by path for better readability
        all_endpoints.sort(key=lambda x: (x.get("path", ""), x.get("method", "")))
        
        return all_endpoints
    
    def _detect_scim_support(self, scraped_data: List[Dict], doc_links: Dict) -> Dict:
        """Detect if cloud supports SCIM provisioning"""
        scim_detected = False
        scim_version = None
        scim_url = doc_links.get("scim_documentation")
        scim_endpoints = []
        
        # Method 1: Check for SCIM endpoints in scraped API paths
        for page in scraped_data:
            endpoints = page.get("api_endpoints", [])
            for ep in endpoints:
                path = ep.get("path", "").lower()
                if "/scim" in path:
                    scim_detected = True
                    scim_endpoints.append(ep.get("path"))
                    # Try to determine version from path
                    if "/scim/v2" in path or "/scim/2" in path:
                        scim_version = "2.0"
                    elif "/scim/v1" in path or "/scim/1" in path:
                        scim_version = "1.1"
        
        # Method 2: Check scraped content for SCIM mentions
        if not scim_detected:
            for page in scraped_data:
                content = page.get("content", "").lower()
                if "scim" in content:
                    scim_detected = True
                    if "scim 2.0" in content or "scim v2" in content or "scim/v2" in content:
                        scim_version = "2.0"
                    elif "scim 1.1" in content or "scim v1" in content:
                        scim_version = "1.1"
                    break
        
        # Method 3: Check documentation URLs
        if not scim_detected and scim_url:
            scim_detected = True
            if "/scim/v2" in scim_url.lower() or "scim-2" in scim_url.lower():
                scim_version = "2.0"
        
        # Default to 2.0 if SCIM detected but version unclear (most common)
        if scim_detected and not scim_version:
            scim_version = "2.0"
        
        logger.info(f"[SCIM] Detected: {scim_detected}, Version: {scim_version}, Endpoints: {len(scim_endpoints)}")
        
        return {
            "enabled": scim_detected,
            "version": scim_version if scim_detected else None,
            "documentation_url": scim_url,
            "operations": ["Users", "Groups"] if scim_detected else [],
            "scim_endpoints": scim_endpoints[:5]  # Include up to 5 example SCIM endpoints
        }
    
    def _detect_api_version(self, scraped_data: List[Dict]) -> str:
        """Detect API version from URLs and content"""
        version_patterns = [r"v(\d+)", r"api/(\d+)", r"version.?(\d+\.\d+)"]
        
        for page in scraped_data:
            url = page.get("url", "")
            for pattern in version_patterns:
                import re
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    return f"v{match.group(1)}"
        
        return "v1"  # Default
    
    def _calculate_confidence_score(self, normalized_data: Dict, scraped_data: List[Dict], classification: Dict) -> float:
        """
        Calculate EXTRACTION confidence score with CLOUD-TYPE AWARE CAPS.
        
        This measures how well we extracted and validated the API, NOT whether
        the cloud supports the operations. These are different concerns.
        
        Confidence levels (CAPPED by cloud type):
        - IAM/Content Management: Max 0.75
        - Collaboration: Max 0.65
        - Developer Platform: Max 0.60
        - Business App: Max 0.55
        """
        # Get dynamic expectations based on cloud type
        from app.cloud_classifier import get_expected_operations_for_cloud
        expected_ops = get_expected_operations_for_cloud(classification)
        EXPECTED_CORE_OPS = len(expected_ops) if expected_ops else 8
        
        # Factor 1: Core operation coverage (40% weight)
        # How many of the 11 core operations did we successfully map?
        core_ops_count = len(normalized_data.get("core_operations", {}))
        coverage_score = min(core_ops_count / EXPECTED_CORE_OPS, 1.0) * 0.4
        
        # Factor 2: Validation quality (35% weight)
        # High validation rejection rate = low confidence in extraction
        total_endpoints = normalized_data.get("total_endpoints_found", 0)
        validated_endpoints = normalized_data.get("validated_endpoints", 0)
        invalid_mappings = len(normalized_data.get("invalid_mappings", []))
        rejected_endpoints = len(normalized_data.get("rejected_endpoints", []))
        
        if total_endpoints > 0:
            validation_pass_rate = validated_endpoints / total_endpoints
            rejection_penalty = (invalid_mappings + rejected_endpoints) / total_endpoints
            validation_score = max(0, (validation_pass_rate - rejection_penalty)) * 0.35
        else:
            validation_score = 0.0
        
        # Factor 3: HTTP method completeness (15% weight)
        # Penalize UNKNOWN methods (indicates incomplete extraction)
        all_ops = list(normalized_data.get("core_operations", {}).values()) + \
                  list(normalized_data.get("extended_operations", {}).values())
        
        total_methods = 0
        known_methods = 0
        if all_ops:
            for op_list in all_ops:
                for op in op_list:
                    total_methods += 1
                    method = op.get("method", "UNKNOWN").upper()
                    if method != "UNKNOWN" and method in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                        known_methods += 1
        
        method_score = (known_methods / total_methods * 0.15) if total_methods > 0 else 0.0
        
        # Factor 4: Data source quality (10% weight)
        # OpenAPI specs = higher confidence than HTML scraping
        source_quality = 0.0
        for page in scraped_data:
            if page.get("source") == "openapi":
                source_quality = 0.10  # Full points for OpenAPI
                break
        else:
            # HTML scraping gets partial credit
            source_quality = 0.05
        
        # Total confidence
        total_score = coverage_score + validation_score + method_score + source_quality
        
        # Cap at 0.95 unless we have perfect validation
        if validation_score < 0.30 or rejected_endpoints > 5:
            total_score = min(total_score, 0.75)  # Cap at "Good" if validation issues
        
        # HARD CAPS by cloud type (NON-NEGOTIABLE)
        category = classification.get("category", "Unknown")
        cloud_type_caps = {
            "Content Management Platform": 0.75,
            "IAM / Directory SaaS": 0.75,
            "Collaboration SaaS": 0.65,
            "Developer Platform": 0.60,
            "Business Application SaaS": 0.55,
        }
        
        cloud_cap = cloud_type_caps.get(category, 0.70)  # Default cap
        if total_score > cloud_cap:
            logger.info(f"[CONFIDENCE] Applying cloud-type cap: {total_score:.2f} → {cloud_cap:.2f} (max for {category})")
            total_score = cloud_cap
        
        # Log breakdown for transparency
        logger.info(f"[CONFIDENCE] Coverage: {coverage_score:.2f} ({core_ops_count}/{EXPECTED_CORE_OPS} ops)")
        logger.info(f"[CONFIDENCE] Validation: {validation_score:.2f} ({validated_endpoints}/{total_endpoints} valid, {invalid_mappings} rejected)")
        logger.info(f"[CONFIDENCE] Methods: {method_score:.2f} ({known_methods}/{total_methods} known)")
        logger.info(f"[CONFIDENCE] Source: {source_quality:.2f}")
        logger.info(f"[CONFIDENCE] CLOUD CAP: {cloud_cap:.2f} ({category})")
        logger.info(f"[CONFIDENCE] FINAL EXTRACTION CONFIDENCE: {total_score:.2f}")
        
        return round(total_score, 2)
    
    def _generate_research_notes(self, normalized_data: Dict, scim_support: Dict, classification: Dict) -> str:
        """
        Generate human-readable research notes with cloud classification context.
        
        CRITICAL: Uses cloud classification to provide accurate interpretation
        of extraction results, distinguishing between extraction failures and
        genuine API limitations.
        """
        notes = []
        
        core_count = len(normalized_data.get("core_operations", {}))
        extended_count = len(normalized_data.get("extended_operations", {}))
        unmapped_count = len(normalized_data.get("unmapped_operations", []))
        invalid_count = len(normalized_data.get("invalid_mappings", []))
        rejected_count = len(normalized_data.get("rejected_endpoints", []))
        total_extracted = normalized_data.get("total_endpoints_found", 0)
        
        category = classification.get("category", "Unknown")
        support_level = classification.get("manage_team_support", "unknown")
        expected_coverage = classification.get("expected_coverage", "Unknown")
        
        # Cloud classification context
        notes.append(f"Cloud Type: {category} (Expected Manage Team Support: {support_level}).")
        
        # Report extraction results
        notes.append(f"Extracted {total_extracted} endpoints and successfully mapped {core_count} core operations + {extended_count} extended operations.")
        
        # Report validation results (transparency)
        if invalid_count > 0:
            notes.append(f"{invalid_count} semantically invalid mappings were rejected during validation.")
        
        if rejected_count > 0:
            notes.append(f"{rejected_count} endpoints failed basic validation checks.")
        
        # SCIM detection (only if actually found)
        if scim_support.get("enabled"):
            scim_ver = scim_support.get('version', '')
            notes.append(f"SCIM {scim_ver} support detected (can be used as alternative to native APIs).")
        
        # Context-aware interpretation
        if support_level == "none":
            notes.append(f"✅ As expected: This cloud type does not provide Manage Team APIs.")
        elif support_level == "full" and core_count < 4:
            notes.append(f"⚠️ Unexpected: {category} clouds typically support Manage Team APIs. Likely an extraction issue - manual verification recommended.")
        elif support_level == "partial" and core_count == 0:
            notes.append(f"⚠️ Possible: This cloud may have limited user/group APIs that were not automatically detected.")
        elif support_level == "limited" and core_count == 0:
            notes.append(f"✅ Expected: {category} clouds typically have limited or no admin lifecycle APIs.")
        elif core_count >= 6:
            notes.append(f"✅ Extraction quality: Good - successfully mapped most core operations.")
        else:
            notes.append(f"Extraction quality: Partial coverage achieved.")
        
        return " ".join(notes)


# Helper function
def research_cloud_api(
    cloud_name: str,
    user_email: str = "",
    force_refresh: bool = False,
    llm=None
) -> Dict:
    """
    Research cloud API and return complete blueprint.
    
    Args:
        cloud_name: Name of the cloud
        user_email: User requesting research
        force_refresh: Force fresh research
        llm: Language model for normalization
        
    Returns:
        Complete research results
    """
    researcher = CloudAPIResearcher(llm)
    return researcher.research_cloud(cloud_name, user_email, force_refresh)
