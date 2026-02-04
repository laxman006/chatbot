# -*- coding: utf-8 -*-
"""
Documentation Link Extractor

Extracts and organizes documentation links from scraped pages with URL validation.
"""

from typing import Dict, List, Optional
import logging
import re
from urllib.parse import urlparse, urljoin
import validators

logger = logging.getLogger(__name__)


class DocumentationLinkExtractor:
    """Extracts and organizes documentation links"""
    
    def __init__(self):
        """Initialize link extractor"""
        pass
    
    def extract_all_links(self, scraped_pages: List[Dict], cloud_name: str) -> Dict:
        """
        Extract all relevant documentation links from scraped pages.
        
        Args:
            scraped_pages: List of scraped page data
            cloud_name: Name of the cloud
            
        Returns:
            Organized dictionary of documentation links
        """
        all_links = {
            "docs_home": None,
            "api_reference": None,
            "getting_started": None,
            "authentication_guide": None,
            "scim_documentation": None,
            "rate_limits": None,
            "changelog": None,
            "best_practices": None,
            "sdks": {},
            "tools": {},
            "additional_resources": []
        }
        
        # Collect all links from all pages
        collected_links = []
        for page in scraped_pages:
            url = page.get("url", "")
            links = page.get("links", [])
            collected_links.extend([(url, link) for link in links])
        
        # Organize links by type
        all_links["docs_home"] = self._find_docs_home(scraped_pages, cloud_name)
        all_links["api_reference"] = self._find_api_reference(collected_links)
        all_links["getting_started"] = self._find_getting_started(collected_links)
        all_links["authentication_guide"] = self._find_auth_guide(collected_links)
        all_links["scim_documentation"] = self._find_scim_docs(collected_links)
        all_links["rate_limits"] = self._find_rate_limits(collected_links)
        all_links["changelog"] = self._find_changelog(collected_links)
        all_links["best_practices"] = self._find_best_practices(collected_links)
        all_links["sdks"] = self._find_sdks(collected_links, cloud_name)
        all_links["tools"] = self._find_tools(collected_links)
        all_links["additional_resources"] = self._find_additional_resources(collected_links)
        
        # Validate all URLs
        all_links = self._validate_links(all_links)
        
        logger.info(f"[EXTRACT] Extracted documentation links for {cloud_name}")
        return all_links
    
    def _find_docs_home(self, scraped_pages: List[Dict], cloud_name: str) -> Optional[str]:
        """Find main documentation home page"""
        if not scraped_pages:
            return None
        
        # Use the first scraped page's base URL as docs home
        first_url = scraped_pages[0].get("url", "")
        if first_url:
            parsed = urlparse(first_url)
            # Return root of documentation site
            return f"{parsed.scheme}://{parsed.netloc}/"
        
        return None
    
    def _find_api_reference(self, links: List[tuple]) -> Optional[str]:
        """Find API reference documentation"""
        keywords = ["api reference", "api/reference", "reference/api", "methods", "/reference"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_getting_started(self, links: List[tuple]) -> Optional[str]:
        """Find getting started guide"""
        keywords = ["getting started", "quick start", "quickstart", "/start", "getting-started"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_auth_guide(self, links: List[tuple]) -> Optional[str]:
        """Find authentication guide"""
        keywords = ["authentication", "/auth", "oauth", "authorization", "auth-guide"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_scim_docs(self, links: List[tuple]) -> Optional[str]:
        """Find SCIM documentation"""
        keywords = ["/scim", "scim api", "scim 2.0", "user provisioning"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_rate_limits(self, links: List[tuple]) -> Optional[str]:
        """Find rate limits documentation"""
        keywords = ["rate limit", "rate-limit", "throttling", "quotas"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_changelog(self, links: List[tuple]) -> Optional[str]:
        """Find changelog/release notes"""
        keywords = ["changelog", "release notes", "/changelog", "releases", "what's new"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_best_practices(self, links: List[tuple]) -> Optional[str]:
        """Find best practices guide"""
        keywords = ["best practices", "best-practices", "guidelines", "recommendations"]
        return self._find_link_by_keywords(links, keywords)
    
    def _find_sdks(self, links: List[tuple], cloud_name: str) -> Dict[str, Dict]:
        """Find SDK links"""
        sdks = {}
        
        sdk_patterns = {
            "python": [r"python", r"py-", r"/python-"],
            "nodejs": [r"node", r"javascript", r"js-", r"/node-"],
            "java": [r"java", r"/java-"],
            "csharp": [r"c#", r"csharp", r"dotnet", r"\.net"],
            "ruby": [r"ruby", r"/ruby-"],
            "php": [r"php", r"/php-"],
            "go": [r"golang", r"/go-", r"go-sdk"],
        }
        
        # Search for GitHub SDK repos
        github_pattern = r"github\.com/[\w-]+/([\w-]+)"
        
        for base_url, link in links:
            link_lower = link.lower()
            
            if "github.com" in link_lower and ("sdk" in link_lower or "client" in link_lower):
                for lang, patterns in sdk_patterns.items():
                    if any(re.search(pattern, link_lower) for pattern in patterns):
                        match = re.search(github_pattern, link)
                        repo_name = match.group(1) if match else f"{cloud_name}-{lang}-sdk"
                        
                        sdks[lang] = {
                            "name": repo_name,
                            "url": link,
                            "install": self._get_install_command(lang, repo_name)
                        }
        
        return sdks
    
    def _find_tools(self, links: List[tuple]) -> Dict[str, str]:
        """Find developer tools (Postman, API explorers, etc.)"""
        tools = {}
        
        for base_url, link in links:
            link_lower = link.lower()
            
            if "postman" in link_lower:
                tools["postman_collection"] = link
            elif "explorer" in link_lower or "playground" in link_lower:
                tools["api_explorer"] = link
            elif "examples" in link_lower and "github" in link_lower:
                tools["code_examples"] = link
        
        return tools
    
    def _find_additional_resources(self, links: List[tuple]) -> List[Dict]:
        """Find additional helpful resources"""
        resources = []
        
        resource_keywords = {
            "tutorials": ["tutorial", "guide", "/guides"],
            "blog": ["blog", "developer blog"],
            "community": ["community", "forum", "discuss"],
            "support": ["support", "help", "contact"],
        }
        
        for base_url, link in links:
            link_lower = link.lower()
            
            for resource_type, keywords in resource_keywords.items():
                if any(keyword in link_lower for keyword in keywords):
                    resources.append({
                        "title": f"{resource_type.title()} Resource",
                        "url": link,
                        "description": f"{resource_type.replace('_', ' ').title()} documentation"
                    })
                    break
        
        # Remove duplicates by URL
        unique_resources = []
        seen_urls = set()
        for resource in resources:
            if resource["url"] not in seen_urls:
                seen_urls.add(resource["url"])
                unique_resources.append(resource)
        
        return unique_resources[:10]  # Limit to 10 additional resources
    
    def _find_link_by_keywords(self, links: List[tuple], keywords: List[str]) -> Optional[str]:
        """Find first link matching any keyword"""
        for base_url, link in links:
            link_lower = link.lower()
            if any(keyword.lower() in link_lower for keyword in keywords):
                return link
        return None
    
    def _get_install_command(self, language: str, package_name: str) -> str:
        """Get installation command for SDK"""
        commands = {
            "python": f"pip install {package_name}",
            "nodejs": f"npm install {package_name}",
            "java": f"// Maven or Gradle dependency for {package_name}",
            "csharp": f"dotnet add package {package_name}",
            "ruby": f"gem install {package_name}",
            "php": f"composer require {package_name}",
            "go": f"go get {package_name}",
        }
        return commands.get(language, f"Install {package_name}")
    
    def _validate_links(self, links_dict: Dict) -> Dict:
        """Validate all URLs in the links dictionary"""
        def validate_url(url):
            """Check if URL is valid"""
            if not url:
                return None
            
            if isinstance(url, str):
                # Validate URL format
                if validators.url(url):
                    return url
                else:
                    logger.warning(f"[VALIDATE] Invalid URL: {url}")
                    return None
            
            return url
        
        # Validate single URL fields
        for key in ["docs_home", "api_reference", "getting_started", "authentication_guide", 
                    "scim_documentation", "rate_limits", "changelog", "best_practices"]:
            if key in links_dict:
                links_dict[key] = validate_url(links_dict[key])
        
        # Validate SDK URLs
        if "sdks" in links_dict:
            for lang, sdk_info in list(links_dict["sdks"].items()):
                if "url" in sdk_info:
                    sdk_info["url"] = validate_url(sdk_info["url"])
                    if not sdk_info["url"]:
                        del links_dict["sdks"][lang]
        
        # Validate tool URLs
        if "tools" in links_dict:
            for tool, url in list(links_dict["tools"].items()):
                validated = validate_url(url)
                if validated:
                    links_dict["tools"][tool] = validated
                else:
                    del links_dict["tools"][tool]
        
        # Validate additional resources
        if "additional_resources" in links_dict:
            validated_resources = []
            for resource in links_dict["additional_resources"]:
                if "url" in resource:
                    resource["url"] = validate_url(resource["url"])
                    if resource["url"]:
                        validated_resources.append(resource)
            links_dict["additional_resources"] = validated_resources
        
        return links_dict


# Helper function
def extract_documentation_links(scraped_pages: List[Dict], cloud_name: str) -> Dict:
    """Extract documentation links from scraped pages"""
    extractor = DocumentationLinkExtractor()
    return extractor.extract_all_links(scraped_pages, cloud_name)
