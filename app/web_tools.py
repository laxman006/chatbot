# -*- coding: utf-8 -*-
"""
Web Search and Scraping Tools for Cloud API Research

Provides web search and documentation scraping capabilities with rate limiting
and safety controls.
"""

from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
import time
import logging
import re
from urllib.parse import urlparse, urljoin
import validators

logger = logging.getLogger(__name__)


class WebSearcher:
    """Web search tool for finding official API documentation"""
    
    def __init__(self, search_api: str = "serpapi", api_key: str = ""):
        """
        Initialize web searcher.
        
        Args:
            search_api: Search API to use ("serper", "serpapi", "google", "bing", "duckduckgo")
            api_key: API key for the search service
        """
        self.search_api = search_api
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CloudFuze API Research Bot/1.0 (+https://cloudfuze.com)"
        })
    
    def search(self, query: str, max_results: int = 10, cloud_name: str = "", official_domain: str = "") -> List[Dict]:
        """
        Search the web for documentation.
        Uses LLM-based URL discovery for cloud API documentation (skips Serper).
        Falls back to DuckDuckGo if LLM-based search doesn't find results.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            cloud_name: Name of cloud provider (for LLM-based search)
            official_domain: Official domain (for LLM-based search)
            
        Returns:
            List of search results with title, url, snippet
        """
        logger.info(f"[SEARCH] Searching for: {query}")
        
        # For cloud API documentation, use LLM-based search directly (skip Serper)
        if cloud_name:
            logger.info(f"[SEARCH] Using LLM-based URL discovery for {cloud_name} (skipping Serper)")
            results = self._search_with_llm(cloud_name, official_domain, query)
            if results:
                logger.info(f"[SEARCH] ✅ Found {len(results)} URLs via LLM-based search")
                return results[:max_results]
            else:
                logger.info(f"[SEARCH] LLM-based search found no results, using DuckDuckGo fallback")
                return self._search_duckduckgo(query, max_results, cloud_name, official_domain)
        
        # For general searches (no cloud_name), try Serper if available
        if self.api_key:
            results = self._search_serper(query, max_results)
            if results:
                logger.info(f"[SEARCH] ✅ Serper API returned {len(results)} results")
                return results
            else:
                logger.info(f"[SEARCH] ⚠️ Serper API unavailable, using DuckDuckGo fallback")
        
        # Final fallback to DuckDuckGo (free, no API key needed)
        logger.info(f"[SEARCH] Using DuckDuckGo (free search)")
        return self._search_duckduckgo(query, max_results, cloud_name, official_domain)
    
    def _search_with_llm(self, cloud_name: str, official_domain: str = "", query: str = "") -> List[Dict]:
        """Use LLM direct query, then domain detector, then LLM-improved DuckDuckGo queries"""
        try:
            # STEP 1: Ask LLM directly (like ChatGPT) for the official API doc URL
            from app.llm_helpers import get_llm_helper
            llm_helper = get_llm_helper()
            if llm_helper:
                logger.info(f"[SEARCH] Asking LLM directly for {cloud_name} API documentation URL")
                llm_urls = llm_helper.ask_for_official_doc_url(cloud_name, official_domain)
                if llm_urls:
                    logger.info(f"[SEARCH] ✅ LLM directly provided {len(llm_urls)} URLs")
                    return llm_urls
            
            # STEP 2: Get actual accessible URLs from domain detector (these are REAL, verified URLs)
            if official_domain:
                from app.domain_detector import UniversalDomainDetector
                detector = UniversalDomainDetector()
                accessible_urls = detector.find_api_documentation_urls(official_domain, cloud_name)
                
                if accessible_urls:
                    results = []
                    for url in accessible_urls:
                        results.append({
                            "title": f"{cloud_name} API Documentation",
                            "url": url,
                            "snippet": f"Verified accessible documentation URL for {cloud_name}",
                            "source": "domain_detector"
                        })
                    logger.info(f"[SEARCH] Found {len(results)} accessible URLs via domain detector")
                    return results
            
            # STEP 3: If no accessible URLs found, use LLM to improve DuckDuckGo search query
            if query:
                improved_query = self._improve_search_query_with_llm(cloud_name, official_domain, query)
                if improved_query and improved_query != query:
                    logger.info(f"[SEARCH] LLM improved query: '{query}' → '{improved_query}'")
                    # Use improved query with DuckDuckGo
                    return self._search_duckduckgo(improved_query, max_results=10, cloud_name=cloud_name, official_domain=official_domain)
            
        except Exception as e:
            logger.error(f"[SEARCH] LLM-assisted search failed: {e}")
        return []
    
    def _improve_search_query_with_llm(self, cloud_name: str, official_domain: str, original_query: str) -> str:
        """Use LLM to improve search query for better DuckDuckGo results"""
        try:
            from app.llm_helpers import get_llm_helper
            llm_helper = get_llm_helper()
            if not llm_helper or not llm_helper.llm:
                return original_query
            
            domain_context = f"Official domain: {official_domain}" if official_domain else ""
            
            prompt = f"""You are a search query optimizer. Improve this search query to find official API documentation.

Cloud: {cloud_name}
{domain_context}
Original query: {original_query}

Goal: Find official API reference documentation (not guides, tutorials, or getting-started pages).

Improve the query to:
1. Target API reference pages specifically
2. Include site restriction if domain is known: site:{official_domain}
3. Use specific terms like "API reference", "endpoint reference", "REST API"
4. Avoid generic terms like "documentation", "guide", "tutorial"

Return ONLY the improved query, nothing else."""
            
            response = llm_helper.llm.invoke(prompt)
            improved = response.content.strip().strip('"\'')
            
            if improved and len(improved) > 10:  # Basic validation
                return improved
                
        except Exception as e:
            logger.debug(f"[SEARCH] Query improvement failed: {e}")
        
        return original_query
    
    def _search_serper(self, query: str, max_results: int) -> List[Dict]:
        """Search using Serper API (Google Search API) - falls back to DuckDuckGo if credits exhausted"""
        try:
            url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "q": query,
                "num": max_results
            }
            
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            
            # Check for credit exhaustion or API errors before parsing
            if response.status_code == 401:
                logger.warning(f"[SEARCH] Serper API: Unauthorized (invalid API key or credits exhausted)")
                return []
            elif response.status_code == 403:
                logger.warning(f"[SEARCH] Serper API: Forbidden (credits exhausted or rate limited)")
                return []
            elif response.status_code == 429:
                logger.warning(f"[SEARCH] Serper API: Rate limited, falling back to DuckDuckGo")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            # Check if response indicates no credits or quota issues
            if isinstance(data, dict):
                error_message = data.get("message", "").lower()
                if any(keyword in error_message for keyword in ["credit", "quota", "limit", "exceeded"]):
                    logger.warning(f"[SEARCH] Serper API: Credits exhausted ({error_message}), falling back to DuckDuckGo")
                    return []
            
            results = []
            for item in data.get("organic", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "serper"
                })
            
            if results:
                logger.info(f"[OK] Found {len(results)} results via Serper API")
            else:
                logger.warning(f"[SEARCH] Serper API returned 0 results, falling back to DuckDuckGo")
            
            return results
            
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors (401, 403, 429, etc.)
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code in [401, 403, 429]:
                    logger.warning(f"[SEARCH] Serper API error {status_code}: Credits may be exhausted, falling back to DuckDuckGo")
                else:
                    logger.error(f"[ERROR] Serper API HTTP error {status_code}: {e}")
            else:
                logger.error(f"[ERROR] Serper API HTTP error: {e}")
            return []
        except Exception as e:
            logger.error(f"[ERROR] Serper API search failed: {e}")
            return []
    
    def _search_serpapi(self, query: str, max_results: int) -> List[Dict]:
        """Search using SerpAPI (Google Search API) - legacy support"""
        try:
            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": self.api_key,
                "num": max_results,
                "engine": "google"
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("organic_results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "serpapi"
                })
            
            logger.info(f"[OK] Found {len(results)} results via SerpAPI")
            return results
            
        except Exception as e:
            logger.error(f"[ERROR] SerpAPI search failed: {e}")
            return []
    
    def _search_duckduckgo(self, query: str, max_results: int, cloud_name: str = "", official_domain: str = "") -> List[Dict]:
        """Search using DuckDuckGo (fallback, no API key needed) with LLM filtering"""
        try:
            from ddgs import DDGS
            
            results = []
            blocked_hosts = {
                "duckduckgo.com",
                "www.duckduckgo.com",
                "search.yahoo.com",
                "search.brave.com",
                "www.google.com",
                "www.bing.com",
                "www.mojeek.com",
                "yandex.com",
                "www.yandex.com",
            }
            with DDGS() as ddgs:
                try:
                    # DDGS.text() returns a list directly - get more results for filtering
                    search_results = ddgs.text(query, max_results=max_results * 2)
                    
                    # Check if results is None or empty
                    if search_results is None:
                        logger.warning(f"[SEARCH] DuckDuckGo returned None for query: {query}")
                        return []
                    
                    # Convert to list if it's an iterator
                    if not isinstance(search_results, list):
                        search_results = list(search_results)
                    
                    logger.info(f"[SEARCH] DuckDuckGo raw results count: {len(search_results)}")
                    
                    raw_results = []
                    for idx, item in enumerate(search_results):
                        if not isinstance(item, dict):
                            logger.warning(f"[SEARCH] Item {idx} is not a dict: {type(item)}")
                            continue
                        
                        # Try different possible key names
                        title = item.get("title") or item.get("Title") or ""
                        url = item.get("href") or item.get("link") or item.get("url") or ""
                        snippet = item.get("body") or item.get("snippet") or item.get("description") or ""
                        
                        if url:
                            url = self._clean_duckduckgo_url(url)
                            try:
                                host = urlparse(url).netloc.lower()
                            except Exception:
                                host = ""
                            if host in blocked_hosts:
                                continue
                            raw_results.append({
                                "title": title,
                                "url": url,
                                "snippet": snippet,
                                "source": "duckduckgo"
                            })
                    
                    # Use LLM to filter and rank results if available
                    if cloud_name and raw_results:
                        filtered_results = self._filter_results_with_llm(raw_results, cloud_name, official_domain)
                        if filtered_results:
                            results = filtered_results[:max_results]
                        else:
                            results = raw_results[:max_results]
                    else:
                        results = raw_results[:max_results]
                    
                    logger.info(f"[OK] Found {len(results)} results via DuckDuckGo")
                    return results
                    
                except Exception as inner_e:
                    logger.error(f"[ERROR] DuckDuckGo search inner exception: {inner_e}")
                    logger.error(f"[ERROR] Exception type: {type(inner_e).__name__}")
                    import traceback
                    logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
                    return []
            
        except Exception as e:
            logger.error(f"[ERROR] DuckDuckGo search failed: {e}")
            logger.error(f"[ERROR] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return []
    
    def _clean_duckduckgo_url(self, url: str) -> str:
        """Extract actual URL from DuckDuckGo redirect"""
        if "uddg=" in url:
            match = re.search(r'uddg=([^&]+)', url)
            if match:
                from urllib.parse import unquote
                return unquote(match.group(1))
        return url
    
    def _filter_results_with_llm(self, results: List[Dict], cloud_name: str, official_domain: str = "") -> List[Dict]:
        """Use LLM to filter and rank DuckDuckGo results to find best documentation URLs"""
        try:
            from app.llm_helpers import get_llm_helper
            import json
            llm_helper = get_llm_helper()
            if not llm_helper or not llm_helper.llm or len(results) <= 3:
                return results  # Return as-is if LLM unavailable or too few results
            
            # Prepare results summary for LLM
            results_summary = []
            for i, result in enumerate(results[:15]):  # Limit to top 15 for LLM
                results_summary.append({
                    "index": i,
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "snippet": result.get("snippet", "")[:200]
                })
            
            domain_context = f"Official domain: {official_domain}" if official_domain else ""
            
            prompt = f"""You are filtering search results to find official API documentation URLs.

Cloud: {cloud_name}
{domain_context}

Search results:
{json.dumps(results_summary, indent=2)}

Select the BEST results that are:
1. Official API reference/documentation pages (not guides, tutorials, getting-started)
2. From the official domain if known
3. Contain actual API endpoint information

Return JSON array of selected indices: [0, 2, 5]
Return ONLY the JSON array, nothing else."""
            
            response = llm_helper.llm.invoke(prompt)
            content = response.content.strip()
            
            # Extract JSON array
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                selected_indices = json.loads(json_match.group(0))
                if isinstance(selected_indices, list):
                    filtered = [results[i] for i in selected_indices if 0 <= i < len(results)]
                    if filtered:
                        logger.info(f"[SEARCH] LLM filtered {len(results)} → {len(filtered)} best results")
                        return filtered
        
        except Exception as e:
            logger.debug(f"[SEARCH] LLM filtering failed: {e}")
        
        return results  # Return original if filtering fails
    
    def filter_official_sources(self, results: List[Dict], cloud_name: str) -> List[Dict]:
        """
        Filter search results to only official sources using strict validation.
        
        Args:
            results: List of search results
            cloud_name: Name of the cloud to filter for
            
        Returns:
            Filtered list of official sources, sorted by relevance score
        """
        from app.domain_detector import UniversalDomainDetector
        
        detector = UniversalDomainDetector()
        
        # Try to detect official domain for stricter filtering
        official_domain = detector.detect_official_domain(cloud_name)
        if official_domain:
            logger.info(f"[FILTER] Using official domain for filtering: {official_domain}")
        else:
            logger.warning(f"[FILTER] Could not detect official domain for {cloud_name}, using lenient filtering")
        
        # Validate and score each result
        validated_results = []
        for result in results:
            url = result["url"]
            is_valid, score, reason = detector.validate_url_for_cloud(url, cloud_name, official_domain)
            
            if is_valid:
                result["_relevance_score"] = score
                result["_validation_reason"] = reason
                validated_results.append(result)
                logger.debug(f"[FILTER] ✓ Accepted: {url} (score={score}, {reason})")
            else:
                logger.debug(f"[FILTER] ✗ Rejected: {url} ({reason})")
        
        # Sort by relevance score (highest first)
        validated_results.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
        
        logger.info(f"[FILTER] Filtered {len(results)} → {len(validated_results)} official sources")
        
        # Log top results
        if validated_results:
            logger.info(f"[FILTER] Top result: {validated_results[0]['url']} (score={validated_results[0]['_relevance_score']})")
        
        return validated_results


class DocumentationScraper:
    """Scrapes API documentation from web pages"""
    
    def __init__(self):
        """Initialize documentation scraper"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CloudFuze API Research Bot/1.0 (+https://cloudfuze.com)"
        })
        self.rate_limit_delay = 2  # seconds between requests
        self.last_request_time = 0
    
    def scrape_page(self, url: str) -> Optional[Dict]:
        """
        Scrape a single documentation page.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dict with page content and metadata
        """
        if not self._is_valid_url(url):
            logger.warning(f"[SKIP] Invalid URL: {url}")
            return None
        
        # Rate limiting
        self._enforce_rate_limit()
        
        try:
            logger.info(f"[SCRAPE] Fetching {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract content
            page_data = {
                "url": url,
                "title": self._extract_title(soup),
                "content": self._extract_content(soup),
                "api_endpoints": self._extract_endpoints(soup),
                "links": self._extract_links(soup, url),
                "code_examples": self._extract_code_blocks(soup),
                "status_code": response.status_code,
            }
            
            logger.info(f"[OK] Scraped {url} - Found {len(page_data['api_endpoints'])} endpoints")
            return page_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[ERROR] Failed to scrape {url}: {e}")
            return None
    
    def scrape_multiple(self, urls: List[str], max_pages: int = 10) -> List[Dict]:
        """
        Scrape multiple documentation pages.
        
        Args:
            urls: List of URLs to scrape
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of scraped page data
        """
        results = []
        for i, url in enumerate(urls[:max_pages]):
            page_data = self.scrape_page(url)
            if page_data:
                results.append(page_data)
            
            # Progress logging
            if (i + 1) % 5 == 0:
                logger.info(f"[PROGRESS] Scraped {i + 1}/{min(len(urls), max_pages)} pages")
        
        return results
    
    def _enforce_rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            logger.debug(f"[RATE LIMIT] Sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format and HTTPS"""
        if not validators.url(url):
            return False
        
        parsed = urlparse(url)
        return parsed.scheme == "https"
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title"""
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        
        h1_tag = soup.find("h1")
        if h1_tag:
            return h1_tag.get_text(strip=True)
        
        return "Untitled"
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content text"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text
        text = soup.get_text(separator="\n", strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    
    def _extract_endpoints(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract API endpoints from page using multiple strategies"""
        endpoints = []
        
        # Strategy 1: Extract from HTML tables (very common in API docs)
        endpoints.extend(self._extract_from_tables(soup))
        
        # Strategy 2: Extract from structured HTML (divs, sections with classes/ids)
        endpoints.extend(self._extract_from_structured_html(soup))
        
        # Strategy 3: Extract from code blocks
        endpoints.extend(self._extract_from_code_blocks(soup))
        
        # Strategy 4: Extract from heading sections (NEW - for single-page docs like Canny)
        endpoints.extend(self._extract_from_heading_sections(soup))
        
        # Strategy 5: Extract from definition lists (NEW - common in API docs)
        endpoints.extend(self._extract_from_definition_lists(soup))
        
        # Strategy 6: Extract from HTTP endpoint blocks (NEW - specific patterns)
        endpoints.extend(self._extract_from_http_blocks(soup))
        
        # Strategy 7: Regex patterns on text (fallback)
        endpoints.extend(self._extract_with_regex(soup))
        
        # Remove duplicates and enrich with context
        unique_endpoints = self._deduplicate_and_enrich(endpoints, soup)
        
        logger.info(f"[EXTRACT] Total unique endpoints after deduplication: {len(unique_endpoints)}")
        
        return unique_endpoints
    
    def _extract_from_tables(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract endpoints from HTML tables (common in API reference docs)"""
        endpoints = []
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            header_row = rows[0] if rows else None
            
            # Try to identify column indices
            method_col = desc_col = endpoint_col = None
            if header_row:
                headers = [th.get_text().strip().lower() for th in header_row.find_all(['th', 'td'])]
                for i, h in enumerate(headers):
                    if any(keyword in h for keyword in ['method', 'verb', 'http']):
                        method_col = i
                    elif any(keyword in h for keyword in ['endpoint', 'path', 'url', 'resource']):
                        endpoint_col = i
                    elif any(keyword in h for keyword in ['description', 'desc', 'purpose', 'action']):
                        desc_col = i
            
            # Extract data rows
            for row in rows[1:]:  # Skip header
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                method = None
                path = None
                description = ""
                
                # Try identified columns
                if method_col is not None and method_col < len(cells):
                    method_text = cells[method_col].get_text().strip().upper()
                    if method_text in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                        method = method_text
                
                if endpoint_col is not None and endpoint_col < len(cells):
                    path = cells[endpoint_col].get_text().strip()
                    # Clean up path
                    if path.startswith('/'):
                        path = path.split()[0]  # Take first word if multiple
                
                if desc_col is not None and desc_col < len(cells):
                    description = cells[desc_col].get_text().strip()
                
                # Fallback: try to extract from any cell
                if not method or not path:
                    for cell in cells:
                        cell_text = cell.get_text().strip()
                        # Try to find method
                        method_match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\b', cell_text, re.IGNORECASE)
                        if method_match and not method:
                            method = method_match.group(1).upper()
                        
                        # Try to find path
                        path_match = re.search(r'(/[\w/\-{}:.]+)', cell_text)
                        if path_match and not path:
                            path = path_match.group(1)
                
                if path and path.startswith('/'):
                    endpoints.append({
                        "method": method or "UNKNOWN",
                        "path": path,
                        "description": description,
                        "operation_name": self._guess_operation_name(path, method, description)
                    })
        
        return endpoints
    
    def _extract_from_structured_html(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract from structured HTML sections"""
        endpoints = []
        
        # Look for common API doc structures
        api_sections = soup.find_all(['div', 'section'], class_=re.compile(r'(endpoint|operation|method|api)', re.I))
        
        for section in api_sections:
            method = None
            path = None
            description = ""
            
            # Look for HTTP method badges/labels
            method_elem = section.find(['span', 'code', 'strong', 'b'], class_=re.compile(r'(method|verb|http)', re.I))
            if method_elem:
                method_text = method_elem.get_text().strip().upper()
                if method_text in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                    method = method_text
            
            # Look for endpoint path
            path_elem = section.find(['code', 'span', 'pre'], class_=re.compile(r'(path|endpoint|url)', re.I))
            if path_elem:
                path = path_elem.get_text().strip()
            
            # Description
            desc_elem = section.find(['p', 'div'], class_=re.compile(r'(description|summary)', re.I))
            if desc_elem:
                description = desc_elem.get_text().strip()
            
            if path and path.startswith('/'):
                endpoints.append({
                    "method": method or "UNKNOWN",
                    "path": path,
                    "description": description,
                    "operation_name": self._guess_operation_name(path, method, description)
                })
        
        return endpoints
    
    def _extract_from_code_blocks(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract from code blocks and pre tags"""
        endpoints = []
        code_blocks = soup.find_all(['code', 'pre'])
        
        for code in code_blocks:
            code_text = code.get_text()
            # Look for method + path on same line
            pattern = r'(GET|POST|PUT|PATCH|DELETE)\s+(/[\w/\-{}:.]+)'
            matches = re.finditer(pattern, code_text, re.IGNORECASE)
            
            for match in matches:
                method, path = match.groups()
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": ""
                })
        
        return endpoints
    
    def _extract_with_regex(self, soup: BeautifulSoup) -> List[Dict]:
        """Fallback regex extraction from full text"""
        endpoints = []
        text = soup.get_text()
        
        # Enhanced patterns
        patterns = [
            r'(GET|POST|PUT|PATCH|DELETE)\s+(/[\w/\-{}:.]+)',  # Method + path
            r'https?://[\w\-.]+(/api/v?\d*/[\w/\-{}:.]+)',     # Full URLs
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) == 2:
                    method, path = match.groups()
                    endpoints.append({
                        "method": method.upper() if hasattr(method, 'upper') else "UNKNOWN",
                        "path": path,
                        "description": "",
                        "operation_name": ""
                    })
        
        return endpoints
    
    def _extract_from_heading_sections(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract endpoints from heading-based sections (h1-h6).
        Common in single-page documentation like Canny, Readme.io, GitBook.
        """
        endpoints = []
        
        # Find all headings
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for heading in headings:
            heading_text = heading.get_text().strip()
            
            # Look for operation names in headings (e.g., "List users", "Create user")
            # Find the next sibling content until the next heading
            content_elements = []
            next_elem = heading.find_next_sibling()
            
            while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                content_elements.append(next_elem)
                next_elem = next_elem.find_next_sibling()
                if len(content_elements) > 20:  # Limit search
                    break
            
            # Look for endpoint URL in the content
            for elem in content_elements:
                elem_text = elem.get_text() if elem else ""
                
                # Look for http:// or https:// endpoint patterns
                http_pattern = r'https?://[^\s]+\.(io|com|net)(/[^\s]+)'
                http_matches = re.findall(http_pattern, elem_text)
                
                for match in http_matches:
                    if isinstance(match, tuple):
                        path = match[1] if len(match) > 1 else match[0]
                    else:
                        path = match
                    
                    if path and path.startswith('/'):
                        # Try to find method
                        method = None
                        method_elem = elem.find(['code', 'span', 'strong'], string=re.compile(r'\b(GET|POST|PUT|PATCH|DELETE)\b', re.I))
                        if method_elem:
                            method = method_elem.get_text().strip().upper()
                        else:
                            # Look in text
                            method_match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\b', elem_text, re.I)
                            if method_match:
                                method = method_match.group(1).upper()
                        
                        endpoints.append({
                            "method": method or "UNKNOWN",
                            "path": path,
                            "description": heading_text,
                            "operation_name": self._guess_operation_name(path, method or "", heading_text)
                        })
                        logger.debug(f"[HEADING] Found: {method} {path} from heading '{heading_text}'")
        
        return endpoints
    
    def _extract_from_definition_lists(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract endpoints from definition lists (dl, dt, dd tags).
        Common in API documentation.
        """
        endpoints = []
        
        # Find all definition lists
        definition_lists = soup.find_all('dl')
        
        for dl in definition_lists:
            terms = dl.find_all('dt')
            definitions = dl.find_all('dd')
            
            # Pair up terms and definitions
            for i, dt in enumerate(terms):
                dd = definitions[i] if i < len(definitions) else None
                
                dt_text = dt.get_text().strip()
                dd_text = dd.get_text().strip() if dd else ""
                
                # Look for method and path in term
                method_match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\b', dt_text, re.I)
                path_match = re.search(r'(/[\w/\-{}:.]+)', dt_text)
                
                if path_match:
                    method = method_match.group(1).upper() if method_match else "UNKNOWN"
                    path = path_match.group(1)
                    
                    endpoints.append({
                        "method": method,
                        "path": path,
                        "description": dd_text[:200],  # Limit description length
                        "operation_name": self._guess_operation_name(path, method, dd_text)
                    })
                    logger.debug(f"[DL] Found: {method} {path}")
        
        return endpoints
    
    def _extract_from_http_blocks(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract endpoints from HTTP blocks - look for specific patterns
        like "Endpoint: https://..." or "Method: POST"
        """
        endpoints = []
        
        # Look for elements with "endpoint" in class or id
        endpoint_elements = soup.find_all(['div', 'section', 'p', 'span'], 
                                         attrs={'class': re.compile(r'endpoint', re.I)})
        endpoint_elements.extend(soup.find_all(['div', 'section', 'p', 'span'], 
                                               attrs={'id': re.compile(r'endpoint', re.I)}))
        
        for elem in endpoint_elements:
            text = elem.get_text()
            
            # Look for "Endpoint:" or "URL:" followed by a path
            endpoint_pattern = r'(?:Endpoint|URL):\s*(https?://[^\s]+|/[\w/\-{}:.]+)'
            endpoint_matches = re.findall(endpoint_pattern, text, re.I)
            
            for url in endpoint_matches:
                # Extract path from full URL
                if url.startswith('http'):
                    parsed = urlparse(url)
                    path = parsed.path
                else:
                    path = url
                
                if not path or not path.startswith('/'):
                    continue
                
                # Look for method in same element or nearby
                method = None
                method_pattern = r'(?:Method|HTTP\s+Method):\s*(GET|POST|PUT|PATCH|DELETE)'
                method_match = re.search(method_pattern, text, re.I)
                if method_match:
                    method = method_match.group(1).upper()
                else:
                    # Look in parent or siblings
                    parent = elem.parent
                    if parent:
                        parent_text = parent.get_text()
                        method_match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\b', parent_text, re.I)
                        if method_match:
                            method = method_match.group(1).upper()
                
                endpoints.append({
                    "method": method or "UNKNOWN",
                    "path": path,
                    "description": "",
                    "operation_name": self._guess_operation_name(path, method or "", "")
                })
                logger.debug(f"[HTTP_BLOCK] Found: {method} {path}")
        
        return endpoints
    
    def _guess_operation_name(self, path: str, method: str, description: str) -> str:
        """
        Guess CloudFuze Manage operation name from path, method, and description.
        Focuses on the 8 essential operations.
        """
        path_lower = path.lower()
        method_upper = method.upper() if method else ""
        desc_lower = description.lower() if description else ""
        
        # Combine path and description for analysis
        combined_text = f"{path_lower} {desc_lower}"
        
        # USER OPERATIONS (Priority: match CloudFuze Manage operations)
        
        # getUsers (list users) - GET /users, /api/users, /v1/users/list, etc.
        if method_upper == 'GET' and 'user' in combined_text:
            if any(indicator in combined_text for indicator in [
                'list', '/users', 'users/list', 'get users', 'retrieve users',
                'fetch users', 'all users'
            ]) and 'member' not in combined_text:
                return "getUsers"
        
        # getAdmins (list admins) - GET /admins, /users?role=admin, etc.
        if method_upper == 'GET' and any(indicator in combined_text for indicator in [
            'admin', 'administrator'
        ]):
            if any(indicator in combined_text for indicator in [
                'list', 'get', 'retrieve', 'fetch'
            ]):
                return "getAdmins"
        
        # createUser - POST /users, POST /api/users/create, etc.
        if (method_upper == 'POST' or 'create' in desc_lower) and 'user' in combined_text:
            if any(indicator in combined_text for indicator in [
                'create', 'add', 'new', 'invite'
            ]) and 'group' not in combined_text:
                return "createUser"
        
        # deleteUser - DELETE /users/{id}, POST /users/delete, etc.
        if (method_upper == 'DELETE' or 'delete' in desc_lower or 'remove' in desc_lower) and 'user' in combined_text:
            if 'group' not in combined_text and 'member' not in combined_text:
                return "deleteUser"
        
        # GROUP OPERATIONS
        
        # getGroups (list groups) - GET /groups, /api/groups/list, etc.
        if method_upper == 'GET' and 'group' in combined_text:
            if any(indicator in combined_text for indicator in [
                'list', '/groups', 'groups/list', 'get groups', 'retrieve groups',
                'fetch groups', 'all groups'
            ]) and 'member' not in combined_text:
                return "getGroups"
        
        # getGroupMembers - GET /groups/{id}/members, /groups/{id}/users, etc.
        if method_upper == 'GET' and 'group' in combined_text:
            if any(indicator in combined_text for indicator in [
                'member', 'user', '/members', '/users'
            ]):
                return "getGroupMembers"
        
        # addUserToGroup - POST /groups/{id}/members, PUT /groups/{id}/users/{uid}, etc.
        if (method_upper in ['POST', 'PUT', 'PATCH'] or 'add' in desc_lower) and 'group' in combined_text:
            if any(indicator in combined_text for indicator in [
                'add', 'member', 'user', 'assign'
            ]) and 'remove' not in combined_text:
                return "addUserToGroup"
        
        # removeUserFromGroup - DELETE /groups/{id}/members/{uid}, POST /groups/remove, etc.
        if (method_upper == 'DELETE' or 'remove' in desc_lower) and 'group' in combined_text:
            if any(indicator in combined_text for indicator in [
                'remove', 'member', 'user', 'delete'
            ]):
                return "removeUserFromGroup"
        
        # FALLBACK: Generic operation names
        if method_upper == 'GET':
            if 'list' in desc_lower or path_lower.endswith('s'):
                return "list"
            return "get"
        elif method_upper == 'POST':
            return "create"
        elif method_upper == 'PUT' or method_upper == 'PATCH':
            return "update"
        elif method_upper == 'DELETE':
            return "delete"
        
        return ""
    
    def _deduplicate_and_enrich(self, endpoints: List[Dict], soup: BeautifulSoup) -> List[Dict]:
        """Remove duplicates and try to enrich incomplete endpoints"""
        unique_endpoints = []
        seen = set()
        
        for ep in endpoints:
            # Clean path
            path = ep.get('path', '').strip()
            if not path or not path.startswith('/'):
                continue
            
            # Remove query parameters
            path = path.split('?')[0].split('#')[0]
            
            method = ep.get('method', 'UNKNOWN')
            key = f"{method}:{path}"
            
            if key not in seen:
                seen.add(key)
                
                # Try to improve UNKNOWN methods by looking at context
                if method == "UNKNOWN":
                    # Search for this path in text with method nearby
                    text_context = soup.get_text()
                    path_pattern = re.escape(path)
                    context_match = re.search(rf'(GET|POST|PUT|PATCH|DELETE)\s+.*?{path_pattern}|{path_pattern}.*?(GET|POST|PUT|PATCH|DELETE)', 
                                            text_context, re.IGNORECASE | re.DOTALL)
                    if context_match:
                        for group in context_match.groups():
                            if group and group.upper() in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                                method = group.upper()
                                ep['method'] = method
                                break
                
                unique_endpoints.append(ep)
        
        return unique_endpoints
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract relevant links from page"""
        links = []
        
        for link in soup.find_all("a", href=True):
            href = link["href"]
            
            # Convert relative URLs to absolute
            absolute_url = urljoin(base_url, href)
            
            # Filter for documentation-related links
            if any(keyword in absolute_url.lower() for keyword in ["api", "doc", "reference", "guide", "auth", "scim"]):
                if absolute_url not in links:
                    links.append(absolute_url)
        
        return links[:50]  # Limit to 50 links per page
    
    def _extract_code_blocks(self, soup: BeautifulSoup) -> List[str]:
        """Extract code examples from page"""
        code_blocks = []
        
        # Find code blocks in <pre>, <code>, or specific classes
        for tag in soup.find_all(["pre", "code"]):
            code_text = tag.get_text(strip=True)
            if len(code_text) > 20 and len(code_text) < 2000:  # Reasonable size
                code_blocks.append(code_text)
        
        return code_blocks[:10]  # Limit to 10 code examples


# --- Documentation crawl (URL collection only, authoritative links) ---

# Path prefixes under which documentation crawl is allowed (segment-based match).
# Used only when authoritative_docs is empty; results are informational only.
DOC_CRAWL_PATH_PREFIXES = (
    "/developers", "/developer", "/docs", "/documentation", "/admin",
    "/api-docs", "/reference", "/api",
)


def _url_on_official_domain(url: str, official_domain: str) -> bool:
    """True if URL's host matches official_domain (www normalized)."""
    try:
        netloc = (urlparse(url).netloc or "").lower().replace("www.", "")
        domain = (official_domain or "").lower().replace("www.", "")
        return domain and (netloc == domain or netloc.endswith("." + domain))
    except Exception:
        return False


def _url_under_doc_roots(url: str) -> bool:
    """True if URL path is under DOC_CRAWL_PATH_PREFIXES (segment-based)."""
    try:
        path = (urlparse(url).path or "").lower()
        return any(seg in path for seg in DOC_CRAWL_PATH_PREFIXES)
    except Exception:
        return False


def crawl_documentation_urls_only(
    seed_urls: List[str],
    official_domain: str,
    max_depth: int = 2,
    max_fetches: int = 80,
    max_links_per_page: int = 25,
    timeout: int = 6,
    delay_seconds: float = 0.4,
) -> List[str]:
    """
    Crawl vendor doc site for URLs only (no content parsing).
    Used only when authoritative_docs is empty; results are informational only.
    Does not affect integration_mode or confidence.
    - Domain: only official_domain (www normalized).
    - Path: only under DOC_CRAWL_PATH_PREFIXES.
    - Max depth 2; fetch with requests.get; parse <a href> only; urljoin.
    - Hard limits: max_fetches, per-page link cap, timeout. Errors skipped.
    """
    if not official_domain or not seed_urls:
        return []
    collected: List[str] = []
    seen_urls: set = set()
    # BFS: (url, depth)
    queue: List[Tuple[str, int]] = []
    for u in seed_urls:
        u = (u or "").strip()
        if not u or u in seen_urls:
            continue
        if not _url_on_official_domain(u, official_domain) or not _url_under_doc_roots(u):
            continue
        seen_urls.add(u)
        collected.append(u)
        queue.append((u, 0))
    fetches = 0
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "CloudFuze API Research Bot/1.0 (+https://cloudfuze.com)"})
        while queue and fetches < max_fetches:
            url, depth = queue.pop(0)
            if depth > max_depth:
                continue
            fetches += 1
            time.sleep(delay_seconds)
            try:
                resp = session.get(url, timeout=timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception:
                continue
            links_added = 0
            for tag in soup.find_all("a", href=True):
                if links_added >= max_links_per_page:
                    break
                href = (tag.get("href") or "").strip()
                if not href or href.startswith("#") or href.startswith("mailto:"):
                    continue
                try:
                    absolute = urljoin(url, href)
                    parsed = urlparse(absolute)
                    if not parsed.scheme or parsed.scheme not in ("http", "https"):
                        continue
                    absolute = absolute.split("#")[0].rstrip("/") or absolute
                except Exception:
                    continue
                if absolute in seen_urls:
                    continue
                if not _url_on_official_domain(absolute, official_domain) or not _url_under_doc_roots(absolute):
                    continue
                seen_urls.add(absolute)
                collected.append(absolute)
                links_added += 1
                if depth + 1 <= max_depth:
                    queue.append((absolute, depth + 1))
        result = list(dict.fromkeys(collected))
        logger.info(f"[DOC CRAWL] Collected {len(result)} URLs (fetches={fetches})")
        return result
    except Exception as e:
        logger.warning(f"[DOC CRAWL] Crawl error (non-fatal): {e}")
        return list(dict.fromkeys(collected))


# --- Enterprise Admin Doc Resolution (capability-first, no inference) ---

# URL is VALID for admin/enterprise docs ONLY if path contains at least one of these.
ENTERPRISE_SURFACE_PATH_PARTS = (
    "/admin", "/team", "/teams", "/enterprise", "/organization", "/workspace",
    "/directory", "/scim", "/reference", "/api/",
)

# Canonical capability doc queries: for FINDING DOC PAGES only (not endpoints).
CAPABILITY_DOC_QUERIES = {
    "users": ["user management api", "admin users api", "directory api"],
    "groups": ["group management api", "team api", "organization groups"],
    "membership": ["add member api", "remove member api"],
    "audit": ["audit logs api", "events api", "activity api"],
}

# Action-style titles (weak signal): suggest API reference pages.
ADMIN_DOC_TITLE_ACTIONS = ("get", "list", "create", "update", "delete", "assign", "remove")

# Exclude pages whose title or prominent content suggests non-API content.
ADMIN_DOC_EXCLUDE_KEYWORDS = ("blog", "tutorial", "quickstart", "getting started", "sdk ", "ui guide", "marketing")

# Content signals (any-two-of for scrapable):
# a) HTTP verbs
ADMIN_DOC_HTTP_VERBS = ("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")
# b) Endpoint-like paths in content
ADMIN_DOC_PATH_INDICATORS = ("/api/", "/team", "/teams", "/users", "/user/", "/groups", "/group/", "/members", "/admin")
# c) Request/response indicators
ADMIN_DOC_REQUEST_RESPONSE = ("curl", "application/json", "Content-Type", "```", "<code>", "JSON")


def enterprise_surface_filter(results: List[Dict]) -> List[Dict]:
    """
    Keep only results whose URL path contains at least one enterprise surface segment.
    Any URL that does not match is discarded immediately.
    """
    filtered = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        try:
            parsed = urlparse(url)
            path = (parsed.path or "").lower()
        except Exception:
            continue
        if any(part in path for part in ENTERPRISE_SURFACE_PATH_PARTS):
            filtered.append(r)
    return filtered


def search_cloud_documentation_capability_first(
    cloud_name: str,
    search_api: str = "duckduckgo",
    api_key: str = "",
    official_domain: Optional[str] = None,
) -> List[Dict]:
    """
    Capability-first discovery: run canonical doc queries for users, groups, membership, audit.
    Returns raw search results (to be enterprise-filtered and validated separately).
    """
    searcher = WebSearcher(search_api, api_key)
    if not official_domain:
        try:
            from app.domain_detector import UniversalDomainDetector
            detector = UniversalDomainDetector()
            official_domain = detector.detect_official_domain(cloud_name)
        except Exception:
            official_domain = None

    all_results = []
    for _cap, queries in CAPABILITY_DOC_QUERIES.items():
        for q in queries:
            query = f"{cloud_name} {q}"
            if official_domain:
                query = f"{query} site:{official_domain}"
            try:
                results = searcher.search(query, max_results=5, cloud_name=cloud_name, official_domain=official_domain or "")
                all_results.extend(results)
                time.sleep(0.5)
            except Exception:
                pass

    # Dedupe by URL
    seen = set()
    unique = []
    for r in all_results:
        u = r.get("url") or ""
        if u and u not in seen:
            seen.add(u)
            unique.append(r)
    return unique


def fetch_page_metadata(url: str, timeout: int = 8) -> Optional[Dict]:
    """
    Lightweight fetch: title + first N chars of body text. No full scrape.
    Returns {"url", "title", "snippet"} or None on failure.
    """
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "CloudFuze API Research Bot/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = ""
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)
        if not title and soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        if not title:
            title = "Untitled"
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        snippet = (text[:4000] if len(text) > 4000 else text)
        return {"url": url, "title": title, "snippet": snippet}
    except Exception:
        return None


def _url_matches_enterprise_surface(url: str) -> bool:
    """True if URL path contains at least one enterprise surface segment."""
    try:
        path = (urlparse(url).path or "").lower()
        return any(part in path for part in ENTERPRISE_SURFACE_PATH_PARTS)
    except Exception:
        return False


def is_scrapable_admin_doc(url: str, title: str, content_snippet: str) -> bool:
    """
    Pre-scrape validation.
    TRUST RULE: If URL path matches enterprise/admin API reference surfaces (same
    enterprise surface filter), the page is scrapable — no content snippet checks.
    Fallback: for URLs that do NOT match enterprise surface, require any two of
    (content HTTP verbs, endpoint paths, request/response indicators, title action).
    """
    # TRUST RULE: official admin API reference URLs matching enterprise surface are scrapable
    if _url_matches_enterprise_surface(url or ""):
        return True

    # Fallback: URLs not on enterprise surface must pass "any two of" content/title rules
    title_lower = (title or "").lower()
    snippet_lower = (content_snippet or "").lower()
    snippet = content_snippet or ""

    if any(ex in title_lower or ex in snippet_lower for ex in ADMIN_DOC_EXCLUDE_KEYWORDS):
        return False

    signal_a = any(v in snippet for v in ADMIN_DOC_HTTP_VERBS)
    signal_b = any(p in snippet_lower for p in ADMIN_DOC_PATH_INDICATORS)
    signal_c = any(r in snippet_lower for r in ADMIN_DOC_REQUEST_RESPONSE)
    signal_e = any(
        title_lower.strip().startswith(a) or (a + " ") in title_lower or (" " + a + " ") in title_lower
        for a in ADMIN_DOC_TITLE_ACTIONS
    )

    signals_true = sum([signal_a, signal_b, signal_c, signal_e])
    return signals_true >= 2


def validate_admin_doc_candidates(
    candidates: List[Dict],
    max_validate: int = 15,
) -> List[Dict]:
    """
    Validate doc pages BEFORE full scraping. Keep only those that pass
    is_scrapable_admin_doc (title + content checks).
    """
    validated = []
    for r in candidates[:max_validate]:
        url = r.get("url")
        if not url:
            continue
        meta = fetch_page_metadata(url)
        if not meta:
            continue
        if is_scrapable_admin_doc(meta.get("url", url) or url, meta.get("title", ""), meta.get("snippet", "")):
            validated.append({
                "url": url,
                "title": meta.get("title", r.get("title", "")),
                "snippet": meta.get("snippet", r.get("snippet", "")),
            })
    return validated


# Helper functions
def search_cloud_documentation(cloud_name: str, search_api: str = "duckduckgo", api_key: str = "") -> List[Dict]:
    """
    Search for cloud API documentation.
    
    Args:
        cloud_name: Name of the cloud
        search_api: Search API to use
        api_key: API key for search service
        
    Returns:
        List of official documentation URLs
    """
    searcher = WebSearcher(search_api, api_key)
    official_domain = None
    try:
        from app.domain_detector import UniversalDomainDetector
        detector = UniversalDomainDetector()
        official_domain = detector.detect_official_domain(cloud_name)
    except Exception:
        official_domain = None
    
    # Perform multiple searches with different queries
    # PRIORITIZE: API Reference pages over guides/tutorials
    queries = [
        f"{cloud_name} API reference get users",  # Specific: get users endpoint
        f"{cloud_name} API reference post users",  # Specific: create user endpoint
        f"{cloud_name} API reference delete users",  # Specific: delete user endpoint
        f"{cloud_name} API reference get groups",  # Specific: get groups endpoint
        f"{cloud_name} API reference users",  # General: user API reference
        f"{cloud_name} API reference groups",  # General: group API reference
        f"{cloud_name} REST API reference",  # General API reference
        f"{cloud_name} developer API documentation",  # Developer docs
        f"{cloud_name} users API endpoint",  # Specific endpoint search
        f"{cloud_name} groups API endpoint",  # Groups endpoint search
        f"{cloud_name} admin management API",  # Admin APIs
    ]
    
    all_results = []
    if official_domain:
        try:
            direct_urls = detector.find_api_documentation_urls(official_domain, cloud_name)
            for url in direct_urls:
                all_results.append({
                    "title": f"{cloud_name} API documentation",
                    "url": url,
                    "snippet": f"Detected documentation URL for {cloud_name}",
                    "source": "domain_probe"
                })
        except Exception:
            pass
    
    if official_domain:
        queries = [f"{query} site:{official_domain}" for query in queries]

    for query in queries:
        # Pass cloud_name and official_domain for LLM fallback
        results = searcher.search(query, max_results=5, cloud_name=cloud_name, official_domain=official_domain)
        all_results.extend(results)
        time.sleep(1)  # Brief delay between searches
    
    # Filter for official sources
    official_results = searcher.filter_official_sources(all_results, cloud_name)
    
    # Remove duplicates by URL
    unique_results = []
    seen_urls = set()
    for result in official_results:
        if result["url"] not in seen_urls:
            seen_urls.add(result["url"])
            unique_results.append(result)
    
    return unique_results


def scrape_documentation_pages(urls: List[str], max_pages: int = 10) -> List[Dict]:
    """
    Scrape multiple documentation pages.
    
    Args:
        urls: List of URLs to scrape
        max_pages: Maximum pages to scrape
        
    Returns:
        List of scraped documentation data
    """
    scraper = DocumentationScraper()
    return scraper.scrape_multiple(urls, max_pages)
