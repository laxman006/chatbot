# -*- coding: utf-8 -*-
"""
OpenAPI/Swagger Spec Parser

Parses OpenAPI 3.x and Swagger 2.x specifications to extract API endpoints.
This is the PRIMARY extraction method for modern APIs.
"""

import logging
import requests
import yaml
import json
from typing import Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class OpenAPIParser:
    """Parser for OpenAPI/Swagger specifications"""
    
    # Known OpenAPI spec URLs for popular clouds (speeds up discovery)
    KNOWN_SPECS = {
        "okta": [
            "https://raw.githubusercontent.com/okta/okta-management-openapi-spec/master/dist/management.yaml",
            "https://developer.okta.com/docs/api/openapi/okta-management/management/tag/User/",
        ],
        "slack": [
            "https://raw.githubusercontent.com/slackapi/slack-api-specs/master/web-api/slack_web_openapi_v2.json",
        ],
        "github": [
            "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
        ],
        "stripe": [
            "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
        ],
        "twilio": [
            "https://raw.githubusercontent.com/twilio/twilio-oai/main/spec/json/twilio_api_v2010.json",
        ],
    }
    
    def __init__(self):
        self.timeout = 30
        self.user_agent = "CloudFuze API Research Bot/1.0"
    
    def detect_openapi_spec(self, url: str) -> Optional[str]:
        """
        Detect if a URL points to or contains an OpenAPI spec.
        
        Args:
            url: URL to check
            
        Returns:
            OpenAPI spec URL if found, None otherwise
        """
        # Common OpenAPI spec locations
        spec_paths = [
            "/openapi.json",
            "/openapi.yaml",
            "/swagger.json",
            "/swagger.yaml",
            "/api-docs",
            "/v1/swagger.json",
            "/v2/swagger.json",
            "/v3/swagger.json",
            "/docs/openapi.json",
            "/api/openapi.json",
        ]
        
        # Try common paths
        from urllib.parse import urlparse, urljoin
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        for path in spec_paths:
            spec_url = urljoin(base_url, path)
            if self._is_valid_spec(spec_url):
                logger.info(f"[OPENAPI] Found spec at: {spec_url}")
                return spec_url
        
        # Check if the URL itself is a spec
        if self._is_valid_spec(url):
            logger.info(f"[OPENAPI] URL is a spec: {url}")
            return url
        
        return None
    
    def find_openapi_specs_in_docs(self, urls: List[str], cloud_name: str = "") -> List[str]:
        """
        Find OpenAPI spec URLs from documentation URLs.
        
        Args:
            urls: List of documentation URLs
            cloud_name: Name of cloud being researched (for known specs)
            
        Returns:
            List of OpenAPI spec URLs found
        """
        spec_urls = []
        
        # STEP 1: Check if we have known specs for this cloud (fastest)
        if cloud_name:
            cloud_key = cloud_name.lower().strip()
            if cloud_key in self.KNOWN_SPECS:
                known_specs = self.KNOWN_SPECS[cloud_key]
                logger.info(f"[OPENAPI] Found {len(known_specs)} known specs for {cloud_name}")
                spec_urls.extend(known_specs)
        
        # STEP 2: Scan provided URLs
        for url in urls:
            # Look for spec links in known locations
            if "github.com" in url:
                # GitHub repos often have specs in /dist or /specs
                spec_url = self._find_github_spec(url)
                if spec_url and spec_url not in spec_urls:
                    spec_urls.append(spec_url)
            
            # Check for OpenAPI indicators in URL
            if any(keyword in url.lower() for keyword in ["openapi", "swagger", "spec", "api-docs"]):
                if url.endswith(('.json', '.yaml', '.yml')):
                    if url not in spec_urls:
                        spec_urls.append(url)
            
            # Try to detect spec from base URL
            detected = self.detect_openapi_spec(url)
            if detected and detected not in spec_urls:
                spec_urls.append(detected)
        
        logger.info(f"[OPENAPI] Found {len(spec_urls)} total potential spec URLs")
        return spec_urls
    
    def parse_spec(self, spec_url: str) -> Optional[Dict]:
        """
        Parse an OpenAPI specification.
        
        Args:
            spec_url: URL to OpenAPI spec file
            
        Returns:
            Parsed spec data with endpoints
        """
        try:
            logger.info(f"[OPENAPI] Parsing spec: {spec_url}")
            
            # Download spec
            response = requests.get(
                spec_url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent}
            )
            response.raise_for_status()
            
            # Parse YAML or JSON
            if spec_url.endswith(('.yaml', '.yml')):
                spec = yaml.safe_load(response.text)
            else:
                spec = response.json()
            
            # Determine spec version
            if 'openapi' in spec:
                version = spec['openapi']
                logger.info(f"[OPENAPI] Detected OpenAPI {version}")
                return self._parse_openapi_3(spec, spec_url)
            elif 'swagger' in spec:
                version = spec['swagger']
                logger.info(f"[OPENAPI] Detected Swagger {version}")
                return self._parse_swagger_2(spec, spec_url)
            else:
                logger.warning(f"[OPENAPI] Unknown spec format: {spec_url}")
                return None
                
        except Exception as e:
            logger.error(f"[OPENAPI] Failed to parse {spec_url}: {e}")
            return None
    
    def _parse_openapi_3(self, spec: Dict, spec_url: str) -> Dict:
        """Parse OpenAPI 3.x specification"""
        endpoints = []
        
        # Extract base info
        info = spec.get('info', {})
        title = info.get('title', 'Unknown API')
        version = info.get('version', '1.0.0')
        description = info.get('description', '')
        
        # Extract servers (base URLs)
        servers = spec.get('servers', [])
        base_url = servers[0].get('url') if servers else ""
        
        # Extract paths (endpoints)
        paths = spec.get('paths', {})
        
        for path, path_item in paths.items():
            # HARD BLOCK: Skip SCIM endpoints (global requirement)
            from config import ALLOW_SCIM
            if not ALLOW_SCIM and '/scim' in path.lower():
                continue
            
            for method, operation in path_item.items():
                # Skip non-HTTP methods (like 'parameters', 'summary', etc.)
                if method.upper() not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']:
                    continue
                
                # Extract operation details
                operation_id = operation.get('operationId', '')
                summary = operation.get('summary', '')
                op_description = operation.get('description', '')
                tags = operation.get('tags', [])
                
                # Determine operation category
                category = self._categorize_endpoint(path, method, tags, summary, operation_id)
                
                endpoint_data = {
                    "method": method.upper(),
                    "path": path,
                    "operation_name": operation_id,
                    "description": summary or op_description,
                    "tags": tags,
                    "category": category,
                    "source": "openapi",
                    "spec_url": spec_url
                }
                
                endpoints.append(endpoint_data)
        
        logger.info(f"[OPENAPI] Extracted {len(endpoints)} endpoints from {title}")
        
        return {
            "api_title": title,
            "api_version": version,
            "api_description": description,
            "base_url": base_url,
            "endpoints": endpoints,
            "total_endpoints": len(endpoints),
            "spec_type": "openapi_3",
            "spec_url": spec_url
        }
    
    def _parse_swagger_2(self, spec: Dict, spec_url: str) -> Dict:
        """Parse Swagger 2.x specification"""
        endpoints = []
        
        # Extract base info
        info = spec.get('info', {})
        title = info.get('title', 'Unknown API')
        version = info.get('version', '1.0.0')
        description = info.get('description', '')
        
        # Base URL
        base_path = spec.get('basePath', '')
        host = spec.get('host', '')
        schemes = spec.get('schemes', ['https'])
        base_url = f"{schemes[0]}://{host}{base_path}" if host else ""
        
        # Extract paths
        paths = spec.get('paths', {})
        
        for path, path_item in paths.items():
            # HARD BLOCK: Skip SCIM endpoints (global requirement)
            from config import ALLOW_SCIM
            if not ALLOW_SCIM and '/scim' in path.lower():
                continue
            
            for method, operation in path_item.items():
                if method.upper() not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']:
                    continue
                
                operation_id = operation.get('operationId', '')
                summary = operation.get('summary', '')
                op_description = operation.get('description', '')
                tags = operation.get('tags', [])
                
                category = self._categorize_endpoint(path, method, tags, summary, operation_id)
                
                endpoint_data = {
                    "method": method.upper(),
                    "path": path,
                    "operation_name": operation_id,
                    "description": summary or op_description,
                    "tags": tags,
                    "category": category,
                    "source": "swagger",
                    "spec_url": spec_url
                }
                
                endpoints.append(endpoint_data)
        
        logger.info(f"[SWAGGER] Extracted {len(endpoints)} endpoints from {title}")
        
        return {
            "api_title": title,
            "api_version": version,
            "api_description": description,
            "base_url": base_url,
            "endpoints": endpoints,
            "total_endpoints": len(endpoints),
            "spec_type": "swagger_2",
            "spec_url": spec_url
        }
    
    def _categorize_endpoint(self, path: str, method: str, tags: List[str], 
                            summary: str, operation_id: str) -> str:
        """Categorize endpoint into CloudFuze categories"""
        path_lower = path.lower()
        method_upper = method.upper()
        summary_lower = summary.lower()
        operation_lower = operation_id.lower()
        tags_lower = [t.lower() for t in tags]
        
        # User operations
        if any(keyword in path_lower for keyword in ['/users', '/user']):
            return "users"
        
        # Group operations
        if any(keyword in path_lower for keyword in ['/groups', '/group', '/teams', '/team']):
            return "groups"
        
        # App/Application operations
        if any(keyword in path_lower for keyword in ['/apps', '/app', '/applications']):
            return "apps"
        
        # Authentication
        if any(keyword in path_lower for keyword in ['/auth', '/oauth', '/token', '/login']):
            return "authentication"
        
        # SCIM
        if '/scim' in path_lower:
            return "scim"
        
        # License operations
        if any(keyword in path_lower for keyword in ['/license', '/subscription']):
            return "licenses"
        
        # Role operations
        if any(keyword in path_lower for keyword in ['/roles', '/role', '/permissions']):
            return "roles"
        
        # Check tags
        if any(tag in tags_lower for tag in ['user', 'users']):
            return "users"
        if any(tag in tags_lower for tag in ['group', 'groups', 'team', 'teams']):
            return "groups"
        
        return "other"
    
    def _is_valid_spec(self, url: str) -> bool:
        """Check if URL points to a valid OpenAPI/Swagger spec"""
        try:
            response = requests.head(url, timeout=5, headers={"User-Agent": self.user_agent}, allow_redirects=True)
            if response.status_code != 200:
                return False
            
            # Check content type
            content_type = response.headers.get('Content-Type', '').lower()
            if any(ct in content_type for ct in ['json', 'yaml', 'yml', 'text/plain']):
                return True
                
        except:
            pass
        
        return False
    
    def _find_github_spec(self, github_url: str) -> Optional[str]:
        """Find OpenAPI spec in a GitHub repository"""
        # Convert GitHub web URL to raw content URL
        if "github.com" in github_url and "/blob/" in github_url:
            raw_url = github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            if raw_url.endswith(('.json', '.yaml', '.yml')):
                return raw_url
        
        # Common spec locations in GitHub repos
        if "github.com" in github_url:
            # Extract repo info
            parts = github_url.split("github.com/")
            if len(parts) > 1:
                repo_path = parts[1].rstrip('/')
                # Remove /tree/branch if present
                if "/tree/" in repo_path:
                    repo_path = repo_path.split("/tree/")[0]
                
                # Try common spec locations
                spec_paths = [
                    f"https://raw.githubusercontent.com/{repo_path}/master/openapi.yaml",
                    f"https://raw.githubusercontent.com/{repo_path}/main/openapi.yaml",
                    f"https://raw.githubusercontent.com/{repo_path}/master/swagger.json",
                    f"https://raw.githubusercontent.com/{repo_path}/main/swagger.json",
                    f"https://raw.githubusercontent.com/{repo_path}/master/dist/management.yaml",
                    f"https://raw.githubusercontent.com/{repo_path}/main/dist/management.yaml",
                ]
                
                for spec_url in spec_paths:
                    if self._is_valid_spec(spec_url):
                        logger.info(f"[GITHUB] Found spec: {spec_url}")
                        return spec_url
        
        return None


def extract_endpoints_from_openapi(urls: List[str], cloud_name: str = "") -> List[Dict]:
    """
    Extract endpoints from OpenAPI specifications.
    
    Args:
        urls: List of documentation URLs
        cloud_name: Name of cloud being researched (for known specs)
        
    Returns:
        List of endpoint dictionaries
    """
    parser = OpenAPIParser()
    all_endpoints = []
    
    # Find OpenAPI specs (tries known specs first if cloud_name provided)
    spec_urls = parser.find_openapi_specs_in_docs(urls, cloud_name)
    
    if not spec_urls:
        logger.info(f"[OPENAPI] No OpenAPI specs found for {cloud_name or 'unknown cloud'}")
        return []
    
    # Parse each spec
    for spec_url in spec_urls:
        spec_data = parser.parse_spec(spec_url)
        if spec_data:
            endpoints = spec_data.get('endpoints', [])
            all_endpoints.extend(endpoints)
            logger.info(f"[OPENAPI] Parsed {len(endpoints)} from {spec_url}")
            logger.info(f"[OPENAPI] Total endpoints so far: {len(all_endpoints)}")
    
    return all_endpoints
