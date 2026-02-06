# -*- coding: utf-8 -*-
"""
JavaScript-Enabled Documentation Scraper

Uses Playwright to render JavaScript and extract API endpoints from modern,
JS-rendered documentation sites.
"""

import logging
import re
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin
import asyncio
import yaml

logger = logging.getLogger(__name__)


class JavaScriptScraper:
    """Scrapes JavaScript-rendered API documentation using Playwright"""
    
    def __init__(self, cloud_name: Optional[str] = None):
        """
        Initialize JavaScript scraper
        
        Args:
            cloud_name: Name of cloud being researched (for LLM context)
        """
        self.browser = None
        self.playwright = None
        self.timeout = 45000  # 45 seconds (increased for slow pages)
        self.cloud_name = cloud_name or "Unknown"
        self.partial_results = []  # Store partial results in case of timeout
        
        # Initialize LLM helper for intelligent validation
        try:
            from app.llm_helpers import get_llm_helper
            self.llm_helper = get_llm_helper()
            logger.info(f"[JS SCRAPER] LLM helper initialized for {self.cloud_name}")
        except Exception as e:
            logger.warning(f"[JS SCRAPER] LLM helper not available: {e}")
            self.llm_helper = None
    
    async def _init_browser(self):
        """Initialize Playwright browser"""
        if self.browser is None:
            try:
                from playwright.async_api import async_playwright
                self.playwright = await async_playwright().start()
                # Use chromium for best compatibility
                self.browser = await self.playwright.chromium.launch(headless=True)
                logger.info("[JS SCRAPER] Playwright browser initialized")
            except Exception as e:
                logger.error(f"[JS SCRAPER] Failed to initialize Playwright: {e}")
                raise
    
    async def _close_browser(self):
        """Close Playwright browser"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def scrape_page_with_js(self, url: str) -> Optional[Dict]:
        """
        Scrape a page with JavaScript rendering enabled.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dict with page content and extracted endpoints
        """
        context = None
        page = None
        
        try:
            logger.info(f"[JS SCRAPER] Rendering {url} with JavaScript")
            
            await self._init_browser()
            
            # Create new context with realistic user agent
            context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True  # Bypass SSL certificate errors for sites with invalid certs
            )
            
            page = await context.new_page()
            
            network_calls = []
            network_index = {}
            
            def handle_request(request):
                try:
                    if request.resource_type not in ("xhr", "fetch"):
                        return
                    key = (request.method, request.url)
                    entry = {
                        "url": request.url,
                        "method": request.method,
                        "resource_type": request.resource_type,
                    }
                    network_index[key] = entry
                    network_calls.append(entry)
                except Exception:
                    return
            
            def handle_response(response):
                try:
                    request = response.request
                    if request.resource_type not in ("xhr", "fetch"):
                        return
                    key = (request.method, request.url)
                    entry = network_index.get(key)
                    if entry is None:
                        entry = {
                            "url": request.url,
                            "method": request.method,
                            "resource_type": request.resource_type,
                        }
                        network_index[key] = entry
                        network_calls.append(entry)
                    entry["status"] = response.status
                    entry["content_type"] = response.headers.get("content-type", "")
                except Exception:
                    return
            
            page.on("request", handle_request)
            page.on("response", handle_response)
            
            # Navigate and wait for content to load
            # Use "domcontentloaded" instead of "networkidle" for faster page loads
            # GitLab docs and many other sites are slow with "networkidle"
            await page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")
            
            # Additional wait for dynamic content
            await page.wait_for_timeout(2000)  # 2 seconds for JS to execute
            
            # Scroll to trigger lazy-loaded content (SPA docs often load on scroll)
            try:
                await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
                await page.evaluate("() => window.scrollTo(0, 0)")
                await page.wait_for_timeout(500)
            except Exception:
                pass
            
            # Get the fully rendered HTML
            html_content = await page.content()
            
            # Extract text content
            text_content = await page.evaluate("""
                () => {
                    // Remove script and style tags
                    const scripts = document.querySelectorAll('script, style');
                    scripts.forEach(el => el.remove());
                    return document.body.innerText;
                }
            """)
            
            # Also extract code blocks content separately (for OpenAPI YAML)
            code_blocks_text = await page.evaluate("""
                () => {
                    const codeBlocks = Array.from(document.querySelectorAll('code, pre'));
                    return codeBlocks.map(cb => cb.innerText).join('\\n---CODE_BLOCK---\\n');
                }
            """)
            
            # Get page title
            title = await page.title()
            
            logger.info(f"[JS SCRAPER] Successfully rendered {url}")
            
            # Extract endpoints from rendered content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # STRATEGY 0: Try to fetch OpenAPI spec file directly if link found
            spec_endpoints, spec_base_url = await self._try_fetch_openapi_spec_file(page, url, soup, network_calls)
            if spec_endpoints:
                logger.info(f"[JS SCRAPER] Fetched {len(spec_endpoints)} endpoints from OpenAPI spec file")
                return {
                    "url": url,
                    "title": title,
                    "content": text_content[:5000],
                    "api_endpoints": spec_endpoints,
                    "base_url": spec_base_url,
                    "source": "openapi_spec_file",
                    "html_length": len(html_content)
                }
            
            # Extract endpoints and base URL
            # Pass both text content and code blocks for better extraction
            endpoints = self._extract_endpoints_from_rendered_page(soup, text_content, code_blocks_text, url)
            
            # NETWORK FALLBACK: Use XHR/fetch calls when docs hide endpoints in JS
            if not endpoints and network_calls:
                network_endpoints = self._extract_endpoints_from_network_calls(network_calls, url)
                if network_endpoints:
                    endpoints = network_endpoints
                    logger.info(f"[JS SCRAPER] Extracted {len(endpoints)} endpoints from network calls")
            
            # LLM FALLBACK DISABLED:
            # LLM-generated endpoints must NEVER be used or rendered as evidence.

            # Extract base URL from endpoints if available
            base_url = None
            if endpoints:
                base_url = endpoints[0].get('base_url')
            
            # If no base URL found, try to extract from page
            if not base_url:
                base_url = self._extract_base_url(soup, text_content)
            
            logger.info(f"[JS SCRAPER] Extracted {len(endpoints)} endpoints from rendered page")
            if base_url:
                logger.info(f"[JS SCRAPER] Found base URL: {base_url}")
            
            # Extract authentication details (OAuth endpoints, scopes) - critical for integration
            auth_details = self._extract_authentication_details(soup, text_content)
            if auth_details:
                logger.info(f"[JS SCRAPER] Found authentication details: {auth_details.get('auth_type', 'unknown')}")
            
            # Extract links to other endpoint reference pages (for overview pages)
            endpoint_links = self._extract_endpoint_reference_links(soup, url)
            
            return {
                "url": url,
                "title": title,
                "content": text_content[:5000],  # Limit content
                "api_endpoints": endpoints,
                "base_url": base_url,
                "authentication": auth_details,
                "endpoint_reference_links": endpoint_links,  # New: links to follow
                "source": "javascript_rendered",
                "html_length": len(html_content)
            }
            
        except Exception as e:
            logger.error(f"[JS SCRAPER] Failed to scrape {url}: {e}")
            return None
            
        finally:
            if page:
                await page.close()
            if context:
                await context.close()
    
    def _extract_endpoints_from_rendered_page(self, soup, text_content: str, code_blocks_text: str = "", page_url: str = "") -> List[Dict]:
        """
        Extract API endpoints from JavaScript-rendered page.
        Prioritizes OpenAPI YAML blocks, curl examples, URL patterns, then structured HTML, then regex patterns.
        
        Args:
            soup: BeautifulSoup object of rendered HTML
            text_content: Plain text content of page
            code_blocks_text: Separated code blocks text (for better YAML extraction)
            page_url: URL of the page being scraped
            
        Returns:
            List of endpoint dictionaries
        """
        endpoints = []
        base_url = None
        
        # STRATEGY 1: Extract OpenAPI YAML from code blocks (HIGHEST PRIORITY)
        # Box and many modern APIs embed OpenAPI specs in YAML code blocks
        yaml_endpoints, detected_base_url = self._extract_from_openapi_yaml(soup, text_content, code_blocks_text)
        if yaml_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(yaml_endpoints)} endpoints from OpenAPI YAML")
            endpoints.extend(yaml_endpoints)
            if detected_base_url:
                base_url = detected_base_url

        # STRATEGY 1a: Extract OpenAPI JSON embedded in script tags (SPA docs)
        script_endpoints, script_base_url = self._extract_from_openapi_json_scripts(soup)
        if script_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(script_endpoints)} endpoints from OpenAPI JSON in scripts")
            endpoints.extend(script_endpoints)
            if script_base_url and not base_url:
                base_url = script_base_url
        
        # STRATEGY 1b: Extract from curl examples (very common in API docs)
        curl_endpoints = self._extract_from_curl_examples(soup, text_content)
        if curl_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(curl_endpoints)} endpoints from curl examples")
            endpoints.extend(curl_endpoints)
        
        # STRATEGY 2: Extract from URL patterns (Box uses /reference/get-users/ → GET /users)
        if page_url:
            url_endpoints = self._extract_from_url_patterns(soup, page_url)
            if url_endpoints:
                logger.info(f"[JS SCRAPER] Extracted {len(url_endpoints)} endpoints from URL patterns")
                endpoints.extend(url_endpoints)
        
        # STRATEGY 3: Extract from structured HTML elements
        # Many docs use structured divs/sections for endpoints
        structured_endpoints = self._extract_from_structured_html(soup)
        if structured_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(structured_endpoints)} endpoints from structured HTML")
            endpoints.extend(structured_endpoints)

        # STRATEGY 2b: Extract from HTML tables (Method | Path columns) - Dropbox and similar HTML reference pages
        table_endpoints = self._extract_from_html_tables(soup)
        if table_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(table_endpoints)} endpoints from HTML tables")
            endpoints.extend(table_endpoints)

        # STRATEGY 2c: Extract method + path from code blocks (request examples without full URL)
        code_request_endpoints = self._extract_method_path_from_code_blocks(soup, text_content, code_blocks_text)
        if code_request_endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(code_request_endpoints)} endpoints from code/request examples")
            endpoints.extend(code_request_endpoints)

        # STRATEGY 3: Extract base URL from documentation
        if not base_url:
            base_url = self._extract_base_url(soup, text_content)
        
        # STRATEGY 4: Regex patterns for common API endpoint formats (FALLBACK)
        # Only if we haven't found enough endpoints
        if len(endpoints) < 3:
            regex_endpoints = self._extract_with_regex_patterns(soup, text_content, base_url)
            if regex_endpoints:
                logger.info(f"[JS SCRAPER] Extracted {len(regex_endpoints)} endpoints via regex")
                endpoints.extend(regex_endpoints)
        
        # Deduplicate and clean
        unique_endpoints = []
        seen = set()
        
        logger.info(f"[JS SCRAPER] Processing {len(endpoints)} raw endpoints before validation")
        
        for ep in endpoints:
            path = ep['path'].strip()
            original_path = path
            
            # Clean path more aggressively
            # Remove query params, fragments, and trailing punctuation
            path = path.split('?')[0].split('#')[0]
            path = re.sub(r'[^\w/\-{}:]+$', '', path)  # Remove trailing non-path chars
            path = path.rstrip('"').rstrip("'").rstrip(',').rstrip('.').rstrip(';')
            
            # Fix concatenated text (e.g., /usersTry -> /users)
            # If path ends with capital letter + lowercase, it's likely concatenated
            if re.search(r'/[a-z]+[A-Z][a-z]+$', path):
                # Try to extract just the valid part
                match = re.search(r'(/[a-z]+(?:/[a-z\-{}]+)*)', path)
                if match:
                    path = match.group(1)
            
            method = ep['method']
            
            # Normalize path for deduplication (handle /2.0/users vs /users)
            # For Box, /2.0/users and /users are the same endpoint
            normalized_path = path
            if path.startswith('/2.0/'):
                # Keep /2.0/ version (preferred)
                normalized_path = path
            elif path.startswith('/') and not path.startswith('/2.0/'):
                # Check if there's a /2.0/ version already seen
                path_with_version = f"/2.0{path}"
                if any(f"{method}:{path_with_version}" in seen or f"{method}:{path_with_version}" == k for k in seen):
                    # Skip this one, we already have the versioned one
                    logger.debug(f"[JS SCRAPER] Skipping {method} {path} (have versioned: {path_with_version})")
                    continue
            
            key = f"{method}:{normalized_path}"
            
            # Only add if valid and not duplicate
            if key in seen:
                logger.debug(f"[JS SCRAPER] Rejected duplicate: {method} {path}")
            elif not self._is_valid_api_endpoint(path):
                logger.info(f"[JS SCRAPER] Rejected invalid: {method} {path} (original: {original_path})")
            else:
                seen.add(key)
                ep['path'] = path  # Keep original format (with /2.0/ if present)
                if base_url and 'base_url' not in ep:
                    ep['base_url'] = base_url
                unique_endpoints.append(ep)
                logger.debug(f"[JS SCRAPER] Accepted: {method} {path}")
            
        logger.info(f"[JS SCRAPER] Final unique endpoints after validation: {len(unique_endpoints)}")
        if unique_endpoints:
            endpoint_strs = [f"{ep['method']} {ep['path']}" for ep in unique_endpoints[:10]]
            logger.info(f"[JS SCRAPER] Endpoints: {endpoint_strs}")
        
        return unique_endpoints
    
    def _extract_from_openapi_yaml(self, soup, text_content: str, code_blocks_text: str = "") -> Tuple[List[Dict], Optional[str]]:
        """
        Extract endpoints from OpenAPI YAML code blocks.
        Returns (endpoints, base_url)
        """
        endpoints = []
        base_url = None
        
        # Find all code blocks that might contain YAML
        # Box and other docs use various structures
        code_blocks = []
        
        # Standard code/pre tags
        code_blocks.extend(soup.find_all(['code', 'pre']))
        
        # Divs with code-related classes
        code_blocks.extend(soup.find_all('div', class_=re.compile(r'code|yaml|openapi|spec|language-yaml|highlight', re.I)))
        
        # Check nested structures (pre > code)
        for pre in soup.find_all('pre'):
            if pre not in code_blocks:
                code_blocks.append(pre)
            for code in pre.find_all('code'):
                if code not in code_blocks:
                    code_blocks.append(code)
        
        # Also check the separated code blocks text (might have better formatting)
        if code_blocks_text:
            code_block_sections = code_blocks_text.split('---CODE_BLOCK---')
            for code_text in code_block_sections:
                code_text = code_text.strip()
                if len(code_text) < 50:
                    continue
                
                # Check if this looks like OpenAPI YAML
                has_openapi = ('openapi' in code_text.lower() or 
                              'paths:' in code_text.lower() or 
                              'swagger' in code_text.lower() or
                              'operationId:' in code_text.lower())
                
                if has_openapi:
                    logger.debug(f"[JS SCRAPER] Found potential OpenAPI YAML in code blocks text (length: {len(code_text)})")
                    try:
                        spec = yaml.safe_load(code_text)
                        if spec and isinstance(spec, dict):
                            if 'servers' in spec and spec['servers']:
                                base_url = spec['servers'][0].get('url', '')
                                logger.info(f"[JS SCRAPER] Found base URL in OpenAPI: {base_url}")
                            
                            if 'paths' in spec:
                                logger.info(f"[JS SCRAPER] Found {len(spec['paths'])} paths in OpenAPI spec")
                                for path, methods in spec['paths'].items():
                                    if not isinstance(methods, dict):
                                        continue
                                    
                                    for method, details in methods.items():
                                        if method.lower() not in ['get', 'post', 'put', 'patch', 'delete']:
                                            continue
                                        
                                        if not isinstance(details, dict):
                                            continue
                                        
                                        operation_id = details.get('operationId', '')
                                        summary = details.get('summary', '')
                                        description = details.get('description', '')
                                        
                                        endpoints.append({
                                            "method": method.upper(),
                                            "path": path,
                                            "description": summary or description,
                                            "operation_name": operation_id,
                                            "source": "openapi_yaml"
                                        })
                                
                                if endpoints:
                                    logger.info(f"[JS SCRAPER] Successfully extracted {len(endpoints)} endpoints from OpenAPI YAML")
                                    return endpoints, base_url
                    except:
                        continue
        
        logger.debug(f"[JS SCRAPER] Checking {len(code_blocks)} potential code blocks for OpenAPI YAML")
        
        for code_block in code_blocks:
            code_text = code_block.get_text()
            
            # Skip if too short
            if len(code_text) < 50:
                continue
            
            # Check if this looks like OpenAPI YAML
            has_openapi = ('openapi' in code_text.lower() or 
                          'paths:' in code_text.lower() or 
                          'swagger' in code_text.lower() or
                          'operationId:' in code_text.lower())
            
            if not has_openapi:
                continue
            
            logger.debug(f"[JS SCRAPER] Found potential OpenAPI YAML block (length: {len(code_text)}, preview: {code_text[:100]}...)")
            
            try:
                # Try to parse as YAML
                spec = yaml.safe_load(code_text)
                
                if not spec or not isinstance(spec, dict):
                    logger.debug(f"[JS SCRAPER] YAML parsed but not a dict")
                    continue
                
                # Extract base URL from servers
                if 'servers' in spec and spec['servers']:
                    base_url = spec['servers'][0].get('url', '')
                    logger.info(f"[JS SCRAPER] Found base URL in OpenAPI: {base_url}")
                
                # Extract endpoints from paths
                if 'paths' in spec:
                    logger.info(f"[JS SCRAPER] Found {len(spec['paths'])} paths in OpenAPI spec")
                    for path, methods in spec['paths'].items():
                        if not isinstance(methods, dict):
                            continue
                        
                        for method, details in methods.items():
                            if method.lower() not in ['get', 'post', 'put', 'patch', 'delete']:
                                continue
                            
                            if not isinstance(details, dict):
                                continue
                            
                            operation_id = details.get('operationId', '')
                            summary = details.get('summary', '')
                            description = details.get('description', '')
                            
                            endpoints.append({
                                "method": method.upper(),
                                "path": path,
                                "description": summary or description,
                                "operation_name": operation_id,
                                "source": "openapi_yaml"
                            })
                    
                    if endpoints:
                        logger.info(f"[JS SCRAPER] Successfully extracted {len(endpoints)} endpoints from OpenAPI YAML")
                            
            except yaml.YAMLError as e:
                # Not valid YAML, skip
                logger.debug(f"[JS SCRAPER] YAML parse error: {e}")
                continue
            except Exception as e:
                logger.debug(f"[JS SCRAPER] Error parsing YAML block: {e}")
                continue
        
        return endpoints, base_url

    def _extract_from_openapi_json_scripts(self, soup) -> Tuple[List[Dict], Optional[str]]:
        """
        Extract OpenAPI JSON from embedded <script> tags (common in SPA docs).
        Returns (endpoints, base_url)
        """
        endpoints = []
        base_url = None

        try:
            script_tags = soup.find_all("script")
            for script in script_tags:
                script_text = script.string or script.get_text() or ""
                if not script_text:
                    continue

                # Quick filter for OpenAPI-like content
                lower = script_text.lower()
                if "openapi" not in lower and "swagger" not in lower:
                    continue
                if "paths" not in lower:
                    continue

                # Try to parse JSON object from the script text
                # Find the first '{' and last '}' to isolate a JSON-like block
                start = script_text.find("{")
                end = script_text.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    continue

                json_blob = script_text[start:end + 1]
                try:
                    spec = json.loads(json_blob)
                except Exception:
                    # Some scripts wrap JSON inside assignments; skip if parse fails
                    continue

                if not isinstance(spec, dict):
                    continue
                if "paths" not in spec:
                    continue

                # Extract base URL
                if "servers" in spec and spec["servers"]:
                    base_url = spec["servers"][0].get("url", base_url)

                # Extract endpoints from paths
                for path, methods in spec.get("paths", {}).items():
                    if not isinstance(methods, dict):
                        continue
                    for method, details in methods.items():
                        method_upper = method.upper()
                        if method_upper not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                            continue
                        endpoints.append({
                            "method": method_upper,
                            "path": path,
                            "description": (details or {}).get("summary", "") if isinstance(details, dict) else "",
                            "operation_name": (details or {}).get("operationId", "") if isinstance(details, dict) else "",
                            "source": "openapi_json_script",
                            "base_url": base_url or ""
                        })

                if endpoints:
                    return endpoints, base_url

        except Exception as e:
            logger.debug(f"[JS SCRAPER] OpenAPI JSON script extraction failed: {e}")

        return endpoints, base_url
    
    def _extract_from_curl_examples(self, soup, text_content: str) -> List[Dict]:
        """
        Extract endpoints from curl examples (very common in API documentation).
        curl examples show the actual API calls with methods and paths.
        """
        endpoints = []
        
        # Find curl examples in code blocks
        # Box format: curl -i -X GET "https://api.box.com/2.0/users"
        curl_patterns = [
            r'curl\s+.*?-X\s+(GET|POST|PUT|PATCH|DELETE)\s+["\'](https?://[^"\']+)["\']',  # With quotes
            r'curl\s+.*?-X\s+(GET|POST|PUT|PATCH|DELETE)\s+(https?://[^\s\)]+)',  # Without quotes
            r'curl\s+.*?(GET|POST|PUT|PATCH|DELETE)\s+["\'](https?://[^"\']+)["\']',  # Method before URL
            r'(GET|POST|PUT|PATCH|DELETE)\s+["\']?(https?://[^"\s\)]+)["\']?',  # Just method + URL
        ]
        
        # Check code blocks for curl examples
        code_blocks = soup.find_all(['code', 'pre'])
        for code_block in code_blocks:
            code_text = code_block.get_text()
            
            if 'curl' not in code_text.lower():
                continue
            
            for pattern in curl_patterns:
                matches = re.finditer(pattern, code_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    method = match.group(1).upper()
                    full_url = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    
                    # Extract path from URL
                    try:
                        from urllib.parse import urlparse, unquote
                        # Clean URL - remove trailing quotes, spaces, etc.
                        full_url = full_url.strip().rstrip('"').rstrip("'").rstrip(')').rstrip(';')
                        parsed = urlparse(full_url)
                        path = parsed.path
                        
                        # Remove query parameters and fragments
                        path = path.split('?')[0].split('#')[0]
                        
                        # Extract base URL
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        
                        if path and self._is_valid_api_endpoint(path):
                            endpoints.append({
                                "method": method,
                                "path": path,
                                "description": "",
                                "operation_name": "",
                                "source": "curl_example",
                                "base_url": base_url
                            })
                            logger.debug(f"[JS SCRAPER] Extracted from curl: {method} {path}")
                    except Exception as e:
                        logger.debug(f"[JS SCRAPER] Error parsing curl URL {full_url}: {e}")
                        continue
        
        # Also check text content for curl-like patterns
        curl_text_patterns = [
            r'curl.*?-X\s+(GET|POST|PUT|PATCH|DELETE).*?["\'](https?://[^"\']+)["\']',  # With quotes
            r'curl.*?-X\s+(GET|POST|PUT|PATCH|DELETE).*?(https?://[^\s\)]+)',  # Without quotes
        ]
        
        for curl_text_pattern in curl_text_patterns:
            matches = re.finditer(curl_text_pattern, text_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                method = match.group(1).upper()
                full_url = match.group(2)
                
                try:
                    from urllib.parse import urlparse
                    # Clean URL
                    full_url = full_url.strip().rstrip('"').rstrip("'").rstrip(')').rstrip(';')
                    parsed = urlparse(full_url)
                    path = parsed.path
                    
                    # Remove query parameters
                    path = path.split('?')[0].split('#')[0]
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    
                    if path and self._is_valid_api_endpoint(path):
                        endpoints.append({
                            "method": method,
                            "path": path,
                            "description": "",
                            "operation_name": "",
                            "source": "curl_example",
                            "base_url": base_url
                        })
                        logger.debug(f"[JS SCRAPER] Extracted from curl text: {method} {path}")
                except Exception as e:
                    logger.debug(f"[JS SCRAPER] Error parsing curl text URL: {e}")
                    continue
        
        return endpoints
    
    def _extract_authentication_details(self, soup, text_content: str) -> Optional[Dict]:
        """
        Extract authentication details (OAuth endpoints, scopes) from documentation.
        Critical for API integration.
        """
        auth_details = {}
        
        # Look for OAuth 2.0 information
        oauth_patterns = [
            r'oauth2?',
            r'authorization.*code',
            r'token.*endpoint',
            r'auth.*endpoint',
        ]
        
        has_oauth = any(re.search(pattern, text_content, re.I) for pattern in oauth_patterns)
        
        if has_oauth:
            auth_details['auth_type'] = 'oauth2'
            
            # ENHANCED: Extract token endpoint with more patterns
            token_patterns = [
                # Direct URL patterns
                r'token\s+endpoint[:\s]+(https?://[^\s\)<]+)',
                r'token\s+url[:\s]+(https?://[^\s\)<]+)',
                r'POST\s+(https?://[^\s\)<]+oauth2?/token[^\s\)<]*)',
                # Box-specific patterns
                r'(https?://api\.box\.com/oauth2/token)',
                r'(https?://[^\s\)<]*\.box\.com/oauth2/token)',
                # Generic patterns
                r'oauth2/token["\']?\s*[:=]\s*["\']?(https?://[^\s\)"\'<]+)',
                r'token_url["\']?\s*[:=]\s*["\']?(https?://[^\s\)"\'<]+)',
                # Code block patterns
                r'curl.*?(https?://[^\s\)<]+oauth2?/token)',
            ]
            
            for pattern in token_patterns:
                match = re.search(pattern, text_content, re.I)
                if match:
                    endpoint = match.group(1).rstrip('.,;\'")><')
                    # Clean up any trailing HTML or markdown
                    endpoint = re.sub(r'[<>\'"]+$', '', endpoint)
                    auth_details['token_endpoint'] = endpoint
                    logger.debug(f"[JS SCRAPER] Found token endpoint: {endpoint}")
                    break
            
            # ENHANCED: Extract authorization endpoint with more patterns
            auth_patterns = [
                # Direct URL patterns
                r'authorization\s+endpoint[:\s]+(https?://[^\s\)<]+)',
                r'auth\s+endpoint[:\s]+(https?://[^\s\)<]+)',
                r'GET\s+(https?://[^\s\)<]+oauth2?/authorize[^\s\)<]*)',
                # Box-specific patterns
                r'(https?://account\.box\.com/api/oauth2/authorize)',
                r'(https?://[^\s\)<]*\.box\.com/[^\s\)<]*oauth2?/authorize)',
                # Generic patterns
                r'oauth2/authorize["\']?\s*[:=]\s*["\']?(https?://[^\s\)"\'<]+)',
                r'authorization_url["\']?\s*[:=]\s*["\']?(https?://[^\s\)"\'<]+)',
                r'authorize_url["\']?\s*[:=]\s*["\']?(https?://[^\s\)"\'<]+)',
            ]
            
            for pattern in auth_patterns:
                match = re.search(pattern, text_content, re.I)
                if match:
                    endpoint = match.group(1).rstrip('.,;\'")><')
                    endpoint = re.sub(r'[<>\'"]+$', '', endpoint)
                    auth_details['authorization_endpoint'] = endpoint
                    logger.debug(f"[JS SCRAPER] Found authorization endpoint: {endpoint}")
                    break
            
            # ENHANCED: Extract scopes with better patterns
            scope_patterns = [
                # Standard patterns
                r'scope[s]?[:\s]+([^\n]+)',
                r'required\s+scope[s]?[:\s]+([^\n]+)',
                r'scope[s]?\s*[:=]\s*["\']([^"\']+)["\']',
                # Code/list patterns
                r'scope[s]?\s*[:=]\s*\[([^\]]+)\]',
                # Box-specific patterns
                r'(manage_users|manage_groups|manage_enterprise)',
                # Table/list item patterns
                r'<li[^>]*>([a-z_\.]+)</li>',
                r'<code>([a-z_\.]+)</code>',
            ]
            
            scopes = []
            for pattern in scope_patterns:
                matches = re.finditer(pattern, text_content, re.I)
                for match in matches:
                    scope_text = match.group(1)
                    # Extract individual scopes (alphanumeric, dots, underscores, hyphens)
                    scope_matches = re.findall(r'[\w\.\-]+', scope_text)
                    for scope in scope_matches:
                        # Filter out common non-scope words
                        if len(scope) > 2 and scope.lower() not in ['the', 'and', 'for', 'with', 'this', 'that', 'from', 'are', 'yes', 'no']:
                            scopes.append(scope)
            
            # Clean up scopes
            if scopes:
                # Remove duplicates and sort
                scopes = sorted(list(set(scopes)))
                # Filter to likely scopes (contain dots, underscores, or common patterns)
                likely_scopes = [s for s in scopes if '.' in s or '_' in s or any(keyword in s.lower() for keyword in ['read', 'write', 'manage', 'admin', 'user', 'group'])]
                if likely_scopes:
                    auth_details['scopes'] = likely_scopes
                elif len(scopes) <= 20:  # If no clear scopes but reasonable number, include all
                    auth_details['scopes'] = scopes
            
            # LLM VALIDATION: Validate OAuth scopes to filter garbage
            if self.llm_helper and auth_details.get('scopes'):
                validated_scopes = self.llm_helper.validate_oauth_scopes(
                    cloud_name=self.cloud_name,
                    extracted_scopes=auth_details['scopes'],
                    context_text=text_content
                )
                # Always replace with validated scopes (even if empty list)
                auth_details['scopes'] = validated_scopes
                if validated_scopes:
                    logger.info(f"[JS SCRAPER] LLM validated {len(validated_scopes)} OAuth scopes for {self.cloud_name}")
                else:
                    logger.info(f"[JS SCRAPER] LLM rejected all scopes as invalid for {self.cloud_name}")
            
            # LLM DETECTION: Detect OAuth endpoints if regex missed them
            if self.llm_helper and (not auth_details.get('token_endpoint') or not auth_details.get('authorization_endpoint')):
                llm_endpoints = self.llm_helper.detect_oauth_endpoints(
                    cloud_name=self.cloud_name,
                    context_text=text_content
                )
                if llm_endpoints.get('token_endpoint') and not auth_details.get('token_endpoint'):
                    auth_details['token_endpoint'] = llm_endpoints['token_endpoint']
                    logger.info(f"[JS SCRAPER] LLM detected token endpoint for {self.cloud_name}: {llm_endpoints['token_endpoint']}")
                if llm_endpoints.get('authorization_endpoint') and not auth_details.get('authorization_endpoint'):
                    auth_details['authorization_endpoint'] = llm_endpoints['authorization_endpoint']
                    logger.info(f"[JS SCRAPER] LLM detected authorization endpoint for {self.cloud_name}: {llm_endpoints['authorization_endpoint']}")
            
            # Check for admin consent requirement
            if re.search(r'admin.*consent|consent.*required|enterprise.*admin', text_content, re.I):
                auth_details['admin_consent_required'] = True
        
        # Look for API key authentication
        if re.search(r'api\s+key|apikey|api_key|developer.*token', text_content, re.I):
            if not auth_details:
                auth_details['auth_type'] = 'api_key'
        
        return auth_details if auth_details else None
    
    def _extract_from_url_patterns(self, soup, page_url: str) -> List[Dict]:
        """
        Extract endpoints from URL patterns in the page.
        Box uses patterns like /reference/get-users/ → GET /2.0/users
        """
        endpoints = []
        
        if page_url:
            # Extract endpoint from URL patterns
            # Box: /reference/get-users/ → GET /2.0/users
            # Box: /reference/post-users/ → POST /2.0/users
            # Box: /reference/get-users-id/ → GET /2.0/users/{id}
            # Box: /reference/get-groups-id-memberships/ → GET /2.0/groups/{id}/memberships
            
            # Check if this is Box (add /2.0/ prefix)
            is_box = 'box.com' in page_url.lower()
            version_prefix = '/2.0' if is_box else ''
            
            # Pattern 1: /reference/get-users/ → GET /2.0/users (for Box)
            pattern1 = r'/reference/(get|post|put|patch|delete)-([\w\-]+)/?$'
            match = re.search(pattern1, page_url, re.I)
            if match:
                method, resource = match.groups()
                path = f"{version_prefix}/{resource}"
                if self._is_valid_api_endpoint(path):
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "description": "",
                        "operation_name": "",
                        "source": "url_pattern"
                    })
                    return endpoints  # Return early if found
            
            # Pattern 2: /reference/get-users-id/ → GET /2.0/users/{id} (for Box)
            pattern2 = r'/reference/(get|post|put|patch|delete)-([\w\-]+)-id/?$'
            match = re.search(pattern2, page_url, re.I)
            if match:
                method, resource = match.groups()
                path = f"{version_prefix}/{resource}/{{id}}"
                if self._is_valid_api_endpoint(path):
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "description": "",
                        "operation_name": "",
                        "source": "url_pattern"
                    })
                    return endpoints
            
            # Pattern 3: /reference/get-groups-id-memberships/ → GET /2.0/groups/{id}/memberships (for Box)
            pattern3 = r'/reference/(get|post|put|patch|delete)-([\w\-]+)-id-([\w\-]+)/?$'
            match = re.search(pattern3, page_url, re.I)
            if match:
                method, resource, subresource = match.groups()
                path = f"{version_prefix}/{resource}/{{id}}/{subresource}"
                if self._is_valid_api_endpoint(path):
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "description": "",
                        "operation_name": "",
                        "source": "url_pattern"
                    })
                    return endpoints
            
            # Pattern 4: /reference/delete-group-memberships-id/ → DELETE /2.0/group_memberships/{id} (for Box)
            pattern4 = r'/reference/(get|post|put|patch|delete)-([\w\-]+)-([\w\-]+)-id/?$'
            match = re.search(pattern4, page_url, re.I)
            if match:
                method, resource1, resource2 = match.groups()
                path = f"{version_prefix}/{resource1}_{resource2}/{{id}}"
                if self._is_valid_api_endpoint(path):
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "description": "",
                        "operation_name": "",
                        "source": "url_pattern"
                    })
                    return endpoints
        
        return endpoints
    
    def _extract_from_structured_html(self, soup) -> List[Dict]:
        """
        Extract endpoints from structured HTML elements (divs, sections with endpoint classes).
        """
        endpoints = []
        
        # Common patterns for endpoint definitions in HTML
        endpoint_selectors = [
            {'class': re.compile(r'endpoint|api-endpoint|operation', re.I)},
            {'data-endpoint': True},
            {'id': re.compile(r'endpoint|api', re.I)},
        ]
        
        for selector in endpoint_selectors:
            elements = soup.find_all(['div', 'section', 'article'], selector)
            
            for element in elements:
                # Try to find method and path
                method_elem = element.find(['span', 'code', 'strong'], class_=re.compile(r'method|http', re.I))
                path_elem = element.find(['span', 'code', 'a'], class_=re.compile(r'path|url|endpoint', re.I))
                
                if not method_elem and not path_elem:
                    # Try text-based extraction
                    # Normalize whitespace first to avoid concatenation issues
                    text = re.sub(r'\s+', ' ', element.get_text())
                    
                    method_match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\b', text, re.I)
                    
                    if method_match:
                        # Extract path more carefully - stop at word boundaries
                        # Look for path patterns: /2.0/users, /users/{id}, /api/v1/users
                        path_patterns = [
                            r'(/[\d\.]+/[\w/\-{}]+)',  # Versioned: /2.0/users
                            r'(/api/v[\d\.]+/[\w/\-{}]+)',  # /api/v1/users
                            r'(/[\w\-]+(?:\{[\w\-]+\})?(?:/[\w\-]+)*)',  # /users/{id}/members
                            r'(/[\w\-]+(?:/[\w\-]+)*)',  # /users/groups
                        ]
                        
                        path = None
                        for pattern in path_patterns:
                            path_match = re.search(pattern, text[method_match.end():method_match.end()+200])
                            if path_match:
                                path = path_match.group(1)
                                # Clean up path - remove trailing non-path characters
                                path = re.sub(r'[^\w/\-{}:].*$', '', path)
                                break
                        
                        if path and self._is_valid_api_endpoint(path):
                            endpoints.append({
                                "method": method_match.group(1).upper(),
                                "path": path,
                                "description": text[:200],
                                "operation_name": "",
                                "source": "structured_html"
                            })
                else:
                    method = method_elem.get_text().strip().upper() if method_elem else "GET"
                    path = path_elem.get_text().strip() if path_elem else ""
                    
                    if path and self._is_valid_api_endpoint(path):
                        endpoints.append({
                            "method": method,
                            "path": path,
                            "description": element.get_text()[:200],
                            "operation_name": "",
                            "source": "structured_html"
                        })
        
        return endpoints

    def _extract_from_html_tables(self, soup) -> List[Dict]:
        """Extract method + path from HTML tables (Method | Path columns). Vendor-agnostic."""
        endpoints = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            header = rows[0]
            cells = header.find_all(["th", "td"])
            header_texts = [c.get_text().strip().lower() for c in cells]
            method_col = None
            path_col = None
            for i, h in enumerate(header_texts):
                if h and ("method" in h or "http" in h or "verb" in h):
                    method_col = i
                if h and ("path" in h or "endpoint" in h or "url" in h or "uri" in h or "route" in h):
                    path_col = i
            if method_col is None or path_col is None:
                continue
            for tr in rows[1:]:
                tds = tr.find_all(["td", "th"])
                if max(method_col, path_col) >= len(tds):
                    continue
                method_raw = tds[method_col].get_text().strip().upper()
                path_raw = tds[path_col].get_text().strip()
                method_match = re.match(r"^(GET|POST|PUT|PATCH|DELETE)", method_raw)
                if not method_match:
                    continue
                method = method_match.group(1)
                path = path_raw.split("?")[0].split("#")[0].strip().rstrip('"').rstrip("'")
                if not path.startswith("/"):
                    path = "/" + path.lstrip()
                if self._is_valid_api_endpoint(path):
                    endpoints.append({
                        "method": method,
                        "path": path,
                        "description": "",
                        "operation_name": "",
                        "source": "html_table"
                    })
        return endpoints

    def _extract_method_path_from_code_blocks(self, soup, text_content: str, code_blocks_text: str = "") -> List[Dict]:
        """Extract METHOD + path from code/text (e.g. GET /team/members). No full URL required."""
        endpoints = []
        combined = (text_content or "") + "\n" + (code_blocks_text or "")
        pattern = r"\b(GET|POST|PUT|PATCH|DELETE)\s+['\"]?(/[\w\.\-/{}\d]+)"
        seen = set()
        for match in re.finditer(pattern, combined, re.IGNORECASE):
            method = match.group(1).upper()
            path = match.group(2).strip().split("?")[0].split("#")[0].rstrip('"').rstrip("'").rstrip(",")
            path = re.sub(r"[^\w/\-{}:].*$", "", path)
            if not path or not path.startswith("/") or not self._is_valid_api_endpoint(path):
                continue
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append({
                "method": method,
                "path": path,
                "description": "",
                "operation_name": "",
                "source": "code_request"
            })
        return endpoints
    
    def _extract_base_url(self, soup, text_content: str) -> Optional[str]:
        """
        Extract base URL from documentation with LLM validation.
        Looks for common patterns and validates with LLM to reject placeholders.
        """
        extracted_url = None
        
        # Pattern 1: Look for "Base URL" or "API Base URL" text
        base_url_patterns = [
            r'base\s+url[:\s]+(https?://[^\s\)]+)',
            r'api\s+base[:\s]+(https?://[^\s\)]+)',
            r'server[:\s]+(https?://[^\s\)]+)',
            r'endpoint[:\s]+(https?://[^\s\)]+)',
        ]
        
        for pattern in base_url_patterns:
            match = re.search(pattern, text_content, re.I)
            if match:
                url = match.group(1).rstrip('.,;')
                if self._is_valid_base_url(url):
                    logger.debug(f"[JS SCRAPER] Regex found base URL: {url}")
                    extracted_url = url
                    break
        
        # Pattern 2: Look in meta tags or structured data
        if not extracted_url:
            base_tag = soup.find('meta', {'name': re.compile(r'base.*url|api.*url', re.I)})
            if base_tag and base_tag.get('content'):
                url = base_tag['content']
                if self._is_valid_base_url(url):
                    extracted_url = url
        
        # Pattern 3: Extract from example URLs (common pattern)
        if not extracted_url:
            # Look for URLs like https://api.box.com/2.0/users
            api_url_pattern = r'(https?://api\.[^\s\)/]+/[v\d\.]+)'
            match = re.search(api_url_pattern, text_content)
            if match:
                url = match.group(1)
                if self._is_valid_base_url(url):
                    extracted_url = url
        
        # LLM VALIDATION: Validate and correct the extracted URL
        if self.llm_helper and extracted_url:
            validated_url = self.llm_helper.validate_base_url(
                cloud_name=self.cloud_name,
                extracted_url=extracted_url,
                context_text=text_content
            )
            if validated_url:
                logger.info(f"[JS SCRAPER] LLM validated base URL for {self.cloud_name}: {validated_url}")
                return validated_url
        
        if extracted_url:
            logger.info(f"[JS SCRAPER] Found base URL (no LLM validation): {extracted_url}")
        
        return extracted_url

    def _extract_endpoints_from_network_calls(self, network_calls: List[Dict], page_url: str) -> List[Dict]:
        """
        Extract endpoints from network calls (XHR/fetch) seen during page render.
        """
        endpoints = []
        seen = set()
        base_host = urlparse(page_url).netloc.lower()
        domain_root = self._get_domain_root(base_host)
        
        for call in network_calls:
            url = call.get("url", "")
            method = (call.get("method") or "").upper()
            content_type = (call.get("content_type") or "").lower()
            
            if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                continue
            if not self._is_potential_api_call(url, domain_root, content_type):
                continue
            
            parsed = urlparse(url)
            path = parsed.path or "/"
            if not self._is_valid_api_endpoint(path):
                continue
            
            base_url = ""
            if parsed.scheme and parsed.netloc:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            key = (method, path, base_url)
            if key in seen:
                continue
            seen.add(key)
            
            endpoints.append({
                "method": method,
                "path": path,
                "description": "",
                "operation_name": "",
                "source": "network_calls",
                "base_url": base_url
            })
        
        return endpoints

    def _is_potential_api_call(self, url: str, domain_root: str, content_type: str) -> bool:
        if not url or not url.startswith("http"):
            return False
        
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return False
        
        if domain_root and not host.endswith(domain_root):
            return False
        
        blocked_domains = [
            "google-analytics.com",
            "googletagmanager.com",
            "segment.io",
            "mixpanel.com",
            "sentry.io",
        ]
        if any(block in host for block in blocked_domains):
            return False
        
        path = parsed.path.lower()
        static_ext = (
            ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
            ".woff", ".woff2", ".ttf", ".ico", ".map", ".webp",
            ".mp4", ".mov"
        )
        if any(path.endswith(ext) for ext in static_ext):
            return False
        
        api_indicators = [
            "/api/", "/api-", "/v1/", "/v2/", "/v3/",
            "/rest/", "/graphql", "/scim", "/oauth", "/auth", "/token"
        ]
        if any(indicator in path for indicator in api_indicators):
            return True
        
        if "application/json" in content_type or "application/vnd" in content_type or "text/json" in content_type:
            return True
        
        return False

    def _get_domain_root(self, hostname: str) -> str:
        if not hostname:
            return ""
        parts = hostname.split(".")
        if len(parts) <= 2:
            return hostname
        return ".".join(parts[-2:])
    
    async def _try_fetch_openapi_spec_file(self, page, page_url: str, soup, network_calls: Optional[List[Dict]] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Try to find and fetch OpenAPI spec file directly.
        Returns (endpoints, base_url)
        """
        endpoints = []
        base_url = None
        
        try:
            # Look for links to OpenAPI spec files
            openapi_links = soup.find_all('a', href=re.compile(r'openapi|swagger|\.json|\.yaml|llms\.txt|spec', re.I))
            
            # Also check text content for spec file URLs
            text_content = soup.get_text()
            url_patterns = [
                r'(https?://[^\s\)]+openapi[^\s\)]*(?:\.json|\.yaml)?)',
                r'(https?://[^\s\)]+swagger[^\s\)]*(?:\.json|\.yaml)?)',
                r'(https?://[^\s\)]+llms\.txt)',
                r'(https?://[^\s\)]+spec[^\s\)]*(?:\.json|\.yaml)?)',
            ]
            
            spec_urls = []
            
            # Collect URLs from links
            for link in openapi_links:
                href = link.get('href', '')
                if href:
                    full_url = urljoin(page_url, href)
                    spec_urls.append(full_url)
            
            # Collect URLs from text
            for pattern in url_patterns:
                matches = re.finditer(pattern, text_content, re.I)
                for match in matches:
                    spec_urls.append(match.group(1))
            
            # Include spec URLs observed during network calls (if any)
            if network_calls:
                for call in network_calls:
                    call_url = call.get("url", "")
                    if not call_url:
                        continue
                    if re.search(r'(openapi|swagger|api-docs|spec|llms\.txt)', call_url, re.I):
                        spec_urls.append(call_url)
                    elif re.search(r'\.(json|yaml|yml)$', call_url, re.I):
                        spec_urls.append(call_url)
            
            # Try common spec file locations
            base_domain = urlparse(page_url).netloc
            common_spec_urls = [
                f"https://{base_domain}/openapi.json",
                f"https://{base_domain}/openapi.yaml",
                f"https://{base_domain}/swagger.json",
                f"https://{base_domain}/api-docs/swagger.json",
                f"https://{base_domain}/llms.txt",
                f"https://{base_domain}/api-reference/openapi.json",
                f"https://{base_domain}/docs/openapi.json",
                f"https://{base_domain}/docs/api/openapi.json",
                f"https://api.{base_domain.replace('developer.', '')}/openapi.json",
            ]
            spec_urls.extend(common_spec_urls)
            
            # Remove duplicates
            spec_urls = list(set(spec_urls))
            
            logger.debug(f"[JS SCRAPER] Checking {len(spec_urls)} potential OpenAPI spec file URLs")
            
            # Try to fetch spec files
            import requests
            for spec_url in spec_urls[:5]:  # Limit to first 5
                try:
                    response = requests.get(spec_url, timeout=10, headers={
                        "User-Agent": "CloudFuze API Research Bot/1.0"
                    })
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        
                        # Try to parse as JSON or YAML
                        if 'json' in content_type or spec_url.endswith('.json'):
                            try:
                                spec = response.json()
                                logger.info(f"[JS SCRAPER] Successfully fetched OpenAPI spec from {spec_url}")
                            except:
                                continue
                        elif 'yaml' in content_type or spec_url.endswith('.yaml') or spec_url.endswith('.yml'):
                            try:
                                spec = yaml.safe_load(response.text)
                                logger.info(f"[JS SCRAPER] Successfully fetched OpenAPI YAML spec from {spec_url}")
                            except:
                                continue
                        else:
                            # Try both JSON and YAML
                            try:
                                spec = response.json()
                                logger.info(f"[JS SCRAPER] Successfully fetched OpenAPI spec (JSON) from {spec_url}")
                            except:
                                try:
                                    spec = yaml.safe_load(response.text)
                                    logger.info(f"[JS SCRAPER] Successfully fetched OpenAPI spec (YAML) from {spec_url}")
                                except:
                                    continue
                        
                        if spec and isinstance(spec, dict):
                            # Extract base URL
                            if 'servers' in spec and spec['servers']:
                                base_url = spec['servers'][0].get('url', '')
                            
                            # Extract endpoints
                            if 'paths' in spec:
                                for path, methods in spec['paths'].items():
                                    if not isinstance(methods, dict):
                                        continue
                                    
                                    for method, details in methods.items():
                                        if method.lower() not in ['get', 'post', 'put', 'patch', 'delete']:
                                            continue
                                        
                                        if not isinstance(details, dict):
                                            continue
                                        
                                        operation_id = details.get('operationId', '')
                                        summary = details.get('summary', '')
                                        description = details.get('description', '')
                                        
                                        endpoints.append({
                                            "method": method.upper(),
                                            "path": path,
                                            "description": summary or description,
                                            "operation_name": operation_id,
                                            "source": "openapi_spec_file",
                                            "base_url": base_url
                                        })
                            
                            if endpoints:
                                logger.info(f"[JS SCRAPER] Extracted {len(endpoints)} endpoints from OpenAPI spec file")
                                return endpoints, base_url
                                
                except Exception as e:
                    logger.debug(f"[JS SCRAPER] Failed to fetch {spec_url}: {e}")
                    continue
                    
        except Exception as e:
            logger.debug(f"[JS SCRAPER] Error checking for OpenAPI spec files: {e}")
        
        return [], None
    
    def _extract_with_regex_patterns(self, soup, text_content: str, base_url: Optional[str]) -> List[Dict]:
        """
        Extract endpoints using regex patterns (fallback method).
        Uses more specific patterns to avoid example URLs.
        """
        endpoints = []
        
        # Normalize text - replace multiple spaces with single space
        text_content = re.sub(r'\s+', ' ', text_content)
        
        # Pattern 1: Box-specific - METHOD /2.0/resource (e.g., GET /2.0/users)
        box_versioned_pattern = r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/2\.0/[\w/\-{}]+)'
        matches = re.finditer(box_versioned_pattern, text_content, re.IGNORECASE)
        
        for match in matches:
            method, path = match.groups()
            # Clean path - stop at non-path characters
            path = re.sub(r'[^\w/\-{}:].*$', '', path)
            if self._is_valid_api_endpoint(path):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": "",
                    "source": "regex_box_versioned"
                })
        
        # Pattern 2: METHOD /version/resource (e.g., GET /v1/users, GET /2.0/users)
        versioned_pattern = r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/[v\d\.]+/[\w/\-{}]+)'
        matches = re.finditer(versioned_pattern, text_content, re.IGNORECASE)
        
        for match in matches:
            method, path = match.groups()
            path = re.sub(r'[^\w/\-{}:].*$', '', path)
            if self._is_valid_api_endpoint(path):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": "",
                    "source": "regex_versioned"
                })
        
        # Pattern 3: /api/vX/resource or /vX/resource
        api_version_pattern = r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/(?:api/)?v[\d\.]+/[\w/\-{}]+)'
        matches = re.finditer(api_version_pattern, text_content, re.IGNORECASE)
        
        for match in matches:
            method, path = match.groups()
            path = re.sub(r'[^\w/\-{}:].*$', '', path)
            if self._is_valid_api_endpoint(path):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": "",
                    "source": "regex_api_version"
                })
        
        # Pattern 4: Box-specific - /users/{user_id}, /groups/{group_id}
        box_path_params = r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/(?:users|groups|group_memberships)(?:/\{[\w\-]+\})?(?:/[\w\-]+)*)'
        matches = re.finditer(box_path_params, text_content, re.IGNORECASE)
        
        for match in matches:
            method, path = match.groups()
            path = re.sub(r'[^\w/\-{}:].*$', '', path)
            if self._is_valid_api_endpoint(path):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": "",
                    "source": "regex_box_path_params"
                })
        
        # Pattern 5: Common REST patterns (/users, /groups, /team, /teams, etc.) - vendor-agnostic
        rest_pattern = r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/(?:users|groups|teams?|team|members|admins|group_memberships)(?:/\{?[\w\-]+\}?)?(?:/[\w\-]+)*)'
        matches = re.finditer(rest_pattern, text_content, re.IGNORECASE)
        
        for match in matches:
            method, path = match.groups()
            path = re.sub(r'[^\w/\-{}:].*$', '', path)
            if self._is_valid_api_endpoint(path):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "description": "",
                    "operation_name": "",
                    "source": "regex_rest"
                })
        
        return endpoints
    
    def _is_valid_base_url(self, url: str) -> bool:
        """Check if URL looks like a valid API base URL"""
        if not url or not url.startswith('http'):
            return False
        
        # Should contain 'api' or be a known API domain pattern
        url_lower = url.lower()
        valid_indicators = ['api.', 'developer.', 'platform.']
        
        return any(indicator in url_lower for indicator in valid_indicators) or 'api' in url_lower
    
    def _is_valid_api_endpoint(self, path: str) -> bool:
        """
        Check if path looks like a valid API endpoint.
        More strict than before - filters out example URLs and concatenated text.
        """
        if not path or not path.startswith('/'):
            return False
        
        # Remove query params and fragments
        path = path.split('?')[0].split('#')[0].rstrip('"').rstrip("'").rstrip(',')
        
        # HARD BLOCK: Reject SCIM endpoints (global requirement)
        from config import ALLOW_SCIM
        if not ALLOW_SCIM and '/scim' in path.lower():
            return False
        
        # Filter out concatenated text (like /usersTry, /groupsNow)
        # Check for capital letter followed by lowercase after a valid path segment
        if re.search(r'/[a-z]+[A-Z][a-z]+', path):
            # This looks like concatenated text (e.g., /usersTry)
            return False
        
        # Reject documentation URL paths (doc page routes, not API request paths)
        doc_markers = ['/reference/', '/documentation/', '/docs/', '/developers/', '/api-docs/']
        path_lower_check = path.lower()
        if any(marker in path_lower_check for marker in doc_markers):
            return False

        # Filter out invalid patterns
        invalid_patterns = [
            r'^/$',  # Just root
            r'^/\w{1,2}$',  # Too short like /v1, /v2
            r'\.(html|htm|php|asp|jpg|png|gif|svg|css|js)$',  # Web assets
            r'/avatar/',  # Avatar URLs (like /api/avatar/large/123)
            r'/image/',  # Image URLs
            r'/static/',  # Static assets
            r'/assets/',  # Assets
            r'/\d{8,}',  # Long numeric IDs (likely example IDs)
            r'/[a-f0-9]{32,}',  # Long hex IDs (likely example IDs)
            r'Try$', r'Now$', r'Here$', r'Click$',  # Common button text concatenations
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, path, re.I):
                return False
        
        # Must have API-like structure
        valid_indicators = [
            r'/v[\d\.]+/',  # Versioned: /v1/, /2.0/
            r'/2\.0/',  # Box-specific version
            r'/api/',  # API prefix
            r'/users', r'/groups', r'/teams', r'/members', r'/group_memberships',  # User/group resources
            r'/admin', r'/management',  # Admin endpoints
            r'/\{',  # Path parameters: /users/{id}
        ]
        
        path_lower = path.lower()
        return any(re.search(pattern, path_lower, re.I) for pattern in valid_indicators)
    
    def _extract_description_near_endpoint(self, text: str, path: str) -> str:
        """Extract description text near an endpoint path"""
        # Find the endpoint in text
        pattern = re.escape(path)
        match = re.search(pattern, text)
        
        if match:
            # Get context before endpoint (likely contains description)
            start = max(0, match.start() - 200)
            context = text[start:match.start()]
            
            # Get last sentence before endpoint
            sentences = context.split('.')
            if sentences:
                desc = sentences[-1].strip()
                return desc[:200]  # Limit length
        
        return ""
    
    def _extract_endpoints_from_network_calls(self, network_calls: List[Dict], page_url: str) -> List[Dict]:
        """
        Extract API endpoints from network XHR/fetch calls captured during page load.
        This is useful when documentation sites load API endpoints dynamically via JavaScript.
        
        Args:
            network_calls: List of network request/response dictionaries
            page_url: URL of the page being scraped (for domain matching)
            
        Returns:
            List of endpoint dictionaries
        """
        endpoints = []
        parsed_page_url = urlparse(page_url)
        page_domain = parsed_page_url.netloc.lower()
        
        # Extract base domain (e.g., api.box.com -> box.com)
        base_domain_parts = page_domain.split('.')
        if len(base_domain_parts) >= 2:
            base_domain = '.'.join(base_domain_parts[-2:])
        else:
            base_domain = page_domain
        
        seen_endpoints = set()
        
        for call in network_calls:
            try:
                url = call.get("url", "")
                method = call.get("method", "GET").upper()
                status = call.get("status", 0)
                content_type = call.get("content_type", "")
                
                if not url:
                    continue
                
                # Parse the network call URL
                parsed_url = urlparse(url)
                call_domain = parsed_url.netloc.lower()
                path = parsed_url.path
                
                # Filter: Only include calls to same domain or subdomain
                if base_domain not in call_domain:
                    continue
                
                # Filter: Only include successful API calls (2xx, 3xx status)
                if status and status >= 400:
                    continue
                
                # Filter: Only include JSON/API-like content types
                if content_type and not any(ct in content_type.lower() for ct in ['json', 'api', 'application', 'text']):
                    # Allow if no content type (some APIs don't set it)
                    if content_type:
                        continue
                
                # Extract path and check if it looks like an API endpoint
                if not path or path == '/':
                    continue
                
                # Clean path
                path = path.split('?')[0].split('#')[0]  # Remove query params and fragments
                
                # Check if this looks like a valid API endpoint
                if not self._is_valid_api_endpoint(path):
                    continue
                
                # Create endpoint key for deduplication
                endpoint_key = (method, path)
                if endpoint_key in seen_endpoints:
                    continue
                seen_endpoints.add(endpoint_key)
                
                # Extract base URL from the network call
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                endpoints.append({
                    "method": method,
                    "path": path,
                    "description": f"Discovered via network call (status: {status})",
                    "operation_name": "",
                    "base_url": base_url,
                    "source": "network_call"
                })
                
            except Exception as e:
                logger.debug(f"[JS SCRAPER] Error processing network call: {e}")
                continue
        
        if endpoints:
            logger.info(f"[JS SCRAPER] Extracted {len(endpoints)} endpoints from {len(network_calls)} network calls")
        
        return endpoints
    
    def _extract_endpoint_reference_links(self, soup, page_url: str) -> List[str]:
        """
        Extract links to endpoint reference pages from an overview page.
        Box uses patterns like /reference/resources/user/ with links to /reference/get-users/, /reference/post-users/, etc.
        
        Returns:
            List of endpoint reference URLs (prioritized: GET/POST first, then others)
        """
        endpoint_links = []
        
        if not page_url:
            return endpoint_links
        
        # Get the base URL from the page URL
        from urllib.parse import urlparse, urljoin
        parsed = urlparse(page_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Find all links on the page
        links = soup.find_all('a', href=True)
        
        # Irrelevant resources to skip (not related to user/group management)
        irrelevant_patterns = [
            r'/files?[-/]',
            r'/folders?[-/]',
            r'/archive',
            r'/collection',
            r'/comment',
            r'/collaboration',
            r'/storage',
            r'/metadata',
            r'/webhook',
            r'/task',
            r'/legal-hold',
            r'/retention',
            r'/classification',
            r'/watermark',
            r'/trash',
            r'/version',
            r'/lock',
            r'/upload',
            r'/download',
            r'/search',
            r'/recent',
            r'/shared',
        ]
        
        for link in links:
            href = link.get('href')
            if not href:
                continue
            
            # Convert relative URLs to absolute
            full_url = urljoin(page_url, href)
            
            # Skip irrelevant resources
            if any(re.search(pattern, full_url, re.I) for pattern in irrelevant_patterns):
                continue
            
            # Check if it's an endpoint reference link
            # Box patterns: /reference/get-users/, /reference/post-users/, /reference/delete-users-id/
            endpoint_patterns = [
                r'/reference/(get|post|put|patch|delete)-',  # Box endpoint pattern
                r'/api/v[\d\.]+/[\w\-]+',  # Versioned API endpoints
                r'/docs/api/[\w\-]+',  # API docs pattern
                r'/api-reference',  # Pax8/modern docs pattern
                r'/reference/',  # Generic reference section
                r'/docs/api-reference',  # API reference section
                r'#/reference',  # Hash-based routes
                r'#/paths',  # OpenAPI hash routes
            ]
            
            link_text = (link.get_text() or "").strip().lower()
            keyword_text = any(k in link_text for k in [
                "user", "users", "group", "groups", "member", "members",
                "admin", "authentication", "auth", "token", "oauth", "access",
                "audit", "log", "logs", "activity"
            ])
            
            if any(re.search(pattern, full_url, re.I) for pattern in endpoint_patterns) or (
                keyword_text and re.search(r'(api|reference|docs)', full_url, re.I)
            ):
                # Check if it's related to users/groups/admin (STRICT)
                relevant_keywords = [
                    'user', 'group', 'team', 'member', 'admin', 'account', 'membership',
                    'audit', 'log', 'logs', 'activity'
                ]
                if any(keyword in full_url.lower() for keyword in relevant_keywords):
                    endpoint_links.append(full_url)
                    logger.debug(f"[JS SCRAPER] Found endpoint reference link: {full_url}")
        
        # Remove duplicates
        endpoint_links = list(set(endpoint_links))
        
        # ENHANCED: Prioritize critical operations for Manage Team
        # Priority 1: GET and POST (listing and creation)
        get_post_links = [url for url in endpoint_links if re.search(r'/(get|post)-', url, re.I)]
        # Priority 2: DELETE (often missed, critical for user/group removal)
        delete_links = [url for url in endpoint_links if re.search(r'/delete-', url, re.I)]
        # Priority 3: PUT/PATCH (updates)
        put_patch_links = [url for url in endpoint_links if re.search(r'/(put|patch)-', url, re.I)]
        # Priority 4: Others
        other_links = [url for url in endpoint_links if not re.search(r'/(get|post|delete|put|patch)-', url, re.I)]
        
        # Return prioritized list: GET/POST first, DELETE second, PUT/PATCH third, then others
        prioritized_links = get_post_links + delete_links + put_patch_links + other_links
        
        if prioritized_links:
            logger.info(f"[JS SCRAPER] Extracted {len(prioritized_links)} endpoint reference links ({len(get_post_links)} GET/POST, {len(delete_links)} DELETE, {len(put_patch_links)} PUT/PATCH, {len(other_links)} others)")
        
        return prioritized_links
    
    def scrape_multiple_pages(self, urls: List[str], max_pages: int = 5) -> List[Dict]:
        """
        Scrape multiple pages with JavaScript rendering (synchronous wrapper).
        
        Args:
            urls: List of URLs to scrape
            max_pages: Maximum number of pages
            
        Returns:
            List of scraped page data
        """
        # Check if we're already in an async context (like FastAPI)
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context (FastAPI) - run in thread pool to avoid loop conflict
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self._scrape_multiple_async(urls, max_pages))
                try:
                    return future.result(timeout=480)  # 8 minute timeout (increased from 5)
                except FutureTimeoutError:
                    logger.warning(f"[JS SCRAPER] ThreadPoolExecutor timeout after 8 minutes - returning partial results ({len(self.partial_results)} pages)")
                    return self.partial_results  # Return whatever we scraped before timeout
        except RuntimeError:
            # No event loop running - safe to use asyncio.run()
            return asyncio.run(self._scrape_multiple_async(urls, max_pages))
    
    async def _scrape_multiple_async(self, urls: List[str], max_pages: int) -> List[Dict]:
        """Async implementation of scraping multiple pages"""
        results = []
        self.partial_results = []  # Reset partial results
        scraped_urls = set()  # Track scraped URLs to avoid duplicates
        urls_to_scrape = list(urls[:max_pages])  # Initial URLs to scrape
        
        # Track pages with actual endpoints (for smarter limiting)
        pages_with_endpoints = 0
        max_useful_pages = max_pages * 2  # Allow scraping more pages to find useful ones
        
        try:
            await self._init_browser()
            
            while urls_to_scrape and pages_with_endpoints < max_pages and len(scraped_urls) < max_useful_pages:
                url = urls_to_scrape.pop(0)
                
                # Strip URL fragments to avoid scraping same page multiple times
                # https://developer.box.com/reference/get-users#param-1 → https://developer.box.com/reference/get-users
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                base_url_no_fragment = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ''))
                
                # Skip if already scraped (check base URL without fragment)
                if base_url_no_fragment in scraped_urls:
                    logger.debug(f"[JS SCRAPER] ⏭️ Skipping {url} (base URL already scraped)")
                    continue
                
                scraped_urls.add(base_url_no_fragment)
                page_data = await self.scrape_page_with_js(url)
                
                if page_data:
                    endpoint_count = len(page_data.get('api_endpoints', []))
                    
                    # Only count pages with actual endpoints toward the limit
                    if endpoint_count > 0:
                        pages_with_endpoints += 1
                        logger.info(f"[JS SCRAPER] ✅ Page {pages_with_endpoints}/{max_pages} with {endpoint_count} endpoints")
                    else:
                        logger.info(f"[JS SCRAPER] ⚠️ Page has 0 endpoints (not counting toward limit)")
                    
                    results.append(page_data)
                    self.partial_results = results.copy()  # Update partial results for timeout recovery
                    
                    # If this page has endpoint reference links, add them to the FRONT of the queue (priority)
                    endpoint_links = page_data.get('endpoint_reference_links', [])
                    if endpoint_links:
                        # Strip fragments from all links and deduplicate
                        unique_base_links = []
                        seen_bases = set()
                        for link in endpoint_links:
                            parsed = urlparse(link)
                            base_link = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ''))
                            if base_link not in seen_bases and base_link not in scraped_urls and base_link not in urls_to_scrape:
                                unique_base_links.append(base_link)
                                seen_bases.add(base_link)
                        
                        if unique_base_links:
                            # Prioritize identity/governance-related pages first to improve
                            # extraction coverage (capability-first evidence gathering).
                            priority_keywords = [
                                "team", "teams",
                                "member", "members", "membership",
                                "audit", "log", "logs", "activity",
                                "user", "users",
                                "group", "groups",
                                "organization", "org",
                            ]

                            def _priority_score(link: str) -> int:
                                lower = (link or "").lower()
                                for i, kw in enumerate(priority_keywords):
                                    if kw in lower:
                                        return i
                                return 10_000

                            unique_base_links.sort(key=lambda u: (_priority_score(u), u))
                            urls_to_scrape = unique_base_links + urls_to_scrape  # Add to front
                            logger.info(f"[JS SCRAPER] 🔼 Prioritized {len(unique_base_links)} unique endpoint pages (fragments stripped)")
                
                logger.info(f"[JS SCRAPER] Progress: {pages_with_endpoints} useful pages, {len(results)} total pages, {len(urls_to_scrape)} in queue")
                
                # Rate limiting (minimal for speed)
                await asyncio.sleep(0.2)  # Reduced to 0.2 seconds for maximum speed
            
            logger.info(f"[JS SCRAPER] Completed: scraped {len(results)} pages ({pages_with_endpoints} with endpoints)")
            return results
            
        finally:
            await self._close_browser()


def scrape_with_javascript(urls: List[str], max_pages: int = 5, cloud_name: Optional[str] = None) -> List[Dict]:
    """
    Convenience function to scrape URLs with JavaScript rendering.
    
    Args:
        urls: List of URLs to scrape
        max_pages: Maximum number of pages to scrape
        cloud_name: Name of cloud being researched (for LLM context)
        
    Returns:
        List of scraped page data with endpoints
    """
    scraper = JavaScriptScraper(cloud_name=cloud_name)
    return scraper.scrape_multiple_pages(urls, max_pages)


def scrape_single_url_with_js(url: str, cloud_name: Optional[str] = None) -> Optional[Dict]:
    """
    Convenience function to scrape a single URL with JavaScript rendering.
    
    Args:
        url: URL to scrape
        cloud_name: Name of cloud being researched (for LLM context)
        
    Returns:
        Scraped page data or None
    """
    async def _scrape():
        scraper = JavaScriptScraper()
        try:
            await scraper._init_browser()
            result = await scraper.scrape_page_with_js(url)
            return result
        finally:
            await scraper._close_browser()
    
    return asyncio.run(_scrape())
