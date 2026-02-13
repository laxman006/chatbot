# -*- coding: utf-8 -*-
"""
Universal Domain Detector

Dynamically detects official domains and documentation URLs for ANY cloud
without requiring hardcoded lists.
"""

import logging
import re
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UniversalDomainDetector:
    """Detects official domains and documentation URLs for any cloud"""
    
    def __init__(self):
        self.timeout = 5
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CloudFuze API Research Bot/1.0"
        })
    
    def detect_official_domain(self, cloud_name: str) -> Optional[str]:
        """
        Detect the official domain for a cloud service.
        
        Args:
            cloud_name: Name of the cloud (e.g., "Slack", "Canny", "Notion")
            
        Returns:
            Official domain (e.g., "slack.com") or None
        """
        # Clean cloud name
        clean_name = cloud_name.lower().replace(" ", "").replace("-", "")
        
        # Try common TLD patterns (most likely first)
        tld_patterns = [
            ".com",
            ".io",
            ".dev",
            ".ai",
            ".co",
        ]
        
        logger.info(f"[DOMAIN] Detecting official domain for '{cloud_name}'")
        
        for tld in tld_patterns:
            domain = f"{clean_name}{tld}"
            if self._verify_domain_exists(domain):
                logger.info(f"[DOMAIN] ✓ Found official domain: {domain}")
                return domain
        
        logger.warning(f"[DOMAIN] Could not detect official domain for '{cloud_name}'")
        return None
    
    def find_api_documentation_urls(self, domain: str, cloud_name: str) -> List[str]:
        """
        Find likely API documentation URLs for a domain.
        
        Args:
            domain: Official domain (e.g., "canny.io")
            cloud_name: Cloud name for context
            
        Returns:
            List of likely documentation URLs
        """
        # Common documentation URL patterns
        patterns = [
            f"https://developers.{domain}",
            f"https://developer.{domain}",
            f"https://docs.{domain}/api",
            f"https://{domain}/docs/api",
            f"https://api.{domain}/docs",
            f"https://{domain}/developers",
            f"https://{domain}/api-docs",
            f"https://docs.{domain}/reference",
            f"https://{domain}/documentation/api",
            f"https://{domain}/api/documentation",
        ]
        
        logger.info(f"[DOMAIN] Checking {len(patterns)} documentation URL patterns for {domain}")
        
        valid_urls = []
        for pattern in patterns:
            if self._check_url_accessible(pattern):
                logger.info(f"[DOMAIN] ✓ Found accessible docs: {pattern}")
                valid_urls.append(pattern)
        
        if not valid_urls:
            logger.warning(f"[DOMAIN] No accessible documentation URLs found for {domain}")
        
        return valid_urls
    
    def validate_url_for_cloud(self, url: str, cloud_name: str, official_domain: Optional[str] = None) -> Tuple[bool, int, str]:
        """
        Validate if a URL is likely official documentation for this cloud.
        
        Args:
            url: URL to validate
            cloud_name: Cloud name
            official_domain: Known official domain (if available)
            
        Returns:
            Tuple of (is_valid, score, reason)
        """
        url_lower = url.lower()
        name_lower = cloud_name.lower().replace(" ", "").replace("-", "")
        
        # REJECT immediately (generic/competitor sites)
        reject_keywords = [
            "wikipedia.org",
            "stackoverflow.com",
            "reddit.com",
            "medium.com",
            "youtube.com",
            "restfulapi.net",
            "tutorialspoint.com",
            "geeksforgeeks.org",
            "w3schools.com",
            # Reject random GitHub repos (not official)
            "github.com/awesome",
            "github.com/topics",
        ]
        
        for keyword in reject_keywords:
            if keyword in url_lower:
                return False, 0, f"Rejected: Generic site ({keyword})"
        
        # REQUIRE: Cloud name in URL (domain or path)
        if name_lower not in url_lower:
            # Exception: If official domain is known, check for that
            if official_domain and official_domain.lower() not in url_lower:
                return False, 0, "Cloud name not in URL"
        
        # Calculate score
        score = 0
        reasons = []
        
        # Official domain match (highest priority)
        if official_domain:
            domain_in_url = official_domain.lower().replace("www.", "")
            if domain_in_url in url_lower:
                score += 50
                reasons.append("Official domain match")
        else:
            # Check for likely official domain
            if f"{name_lower}.com" in url_lower or f"{name_lower}.io" in url_lower or f"{name_lower}.dev" in url_lower:
                score += 40
                reasons.append("Likely official domain")
        
        # Developer/API subdomain (high priority)
        if "developers." in url_lower or "developer." in url_lower:
            score += 20
            reasons.append("Developer subdomain")
        
        if "api." in url_lower:
            score += 15
            reasons.append("API subdomain")
        
        # CRITICAL: Prioritize API REFERENCE over GUIDES
        # Reference pages have actual endpoints, guides are tutorials
        if "/reference/" in url_lower or "/api-reference" in url_lower:
            score += 30  # Highest priority for reference docs
            reasons.append("API Reference page (HIGH PRIORITY)")
        elif "/docs/api" in url_lower or "/api/" in url_lower:
            score += 25
            reasons.append("API documentation")
        elif "/guide" in url_lower or "/tutorial" in url_lower:
            score -= 10  # Lower priority for guides
            reasons.append("Guide page (lower priority)")
        
        # Documentation paths (general)
        doc_indicators = ["/docs/", "/documentation/"]
        for indicator in doc_indicators:
            if indicator in url_lower and "/guide" not in url_lower:
                score += 10
                reasons.append(f"Has {indicator}")
                break

        # Extra penalty for getting-started content when official domain is known
        if official_domain:
            guide_keywords = [
                "/guide",
                "/tutorial",
                "/getting-started",
                "/getting_started",
                "/gettingstarted",
                "/quickstart",
                "/quick-start",
                "/overview",
                "apisforbeginners",
            ]
            if any(keyword in url_lower for keyword in guide_keywords):
                if "/reference/" not in url_lower and "/api-reference" not in url_lower:
                    score -= 20
                    reasons.append("Getting-started content (deprioritized)")
        
        # OAuth/Authentication (lower priority - these are setup guides, not endpoint refs)
        if "oauth" in url_lower or "authentication" in url_lower or "auth" in url_lower:
            if "/reference/" not in url_lower:
                score += 3  # Lower bonus for auth guides
                reasons.append("Auth docs")
            else:
                score += 8  # Higher if it's auth API reference
                reasons.append("Auth API reference")
        
        # HTTPS required
        if not url_lower.startswith("https://"):
            score -= 20
            reasons.append("Not HTTPS")
        
        is_valid = score >= 30  # Threshold
        reason = "; ".join(reasons) if reasons else "No indicators"
        
        logger.debug(f"[VALIDATE] {url}: score={score}, valid={is_valid}, reason={reason}")
        
        return is_valid, score, reason
    
    def _verify_domain_exists(self, domain: str) -> bool:
        """Check if a domain exists and is accessible"""
        try:
            url = f"https://{domain}"
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            # Accept any non-error response (200-399)
            return 200 <= response.status_code < 400
        except Exception as e:
            logger.debug(f"[DOMAIN] Domain {domain} not accessible: {e}")
            return False
    
    def _check_url_accessible(self, url: str) -> bool:
        """Check if a URL is accessible"""
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return 200 <= response.status_code < 400
        except Exception:
            return False
    
    def extract_domain_from_url(self, url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        domain = parsed.netloc
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain


def detect_cloud_domain(cloud_name: str) -> Optional[str]:
    """
    Convenience function to detect official domain for a cloud.
    
    Args:
        cloud_name: Cloud service name
        
    Returns:
        Official domain or None
    """
    detector = UniversalDomainDetector()
    return detector.detect_official_domain(cloud_name)


def find_documentation_urls(cloud_name: str) -> List[str]:
    """
    Convenience function to find documentation URLs for a cloud.
    
    Args:
        cloud_name: Cloud service name
        
    Returns:
        List of likely documentation URLs
    """
    detector = UniversalDomainDetector()
    official_domain = detector.detect_official_domain(cloud_name)
    
    if official_domain:
        return detector.find_api_documentation_urls(official_domain, cloud_name)
    
    return []
