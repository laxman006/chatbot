# -*- coding: utf-8 -*-
"""
SharePoint Authentication Module

Handles authentication with SharePoint using Microsoft Graph API
and SharePoint REST API with application permissions.
"""

import os
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json

class SharePointAuthenticator:
    """Handles SharePoint authentication using client credentials flow."""
    
    def __init__(self):
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = os.getenv("MICROSOFT_TENANT", "cloudfuze.com")
        self.access_token = None
        self.sharepoint_token = None
        self.token_expires_at = None
        
        if not self.client_id or not self.client_secret:
            raise ValueError("MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET are required for SharePoint authentication")
    
    def get_access_token(self) -> str:
        """Get a valid access token for SharePoint API."""
        # Check if we have a valid token
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token
        
        # Get new token for SharePoint
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        # Use Graph scope (needed for getting site info and page lists)
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post(token_url, data=token_data, timeout=30)
            response.raise_for_status()
            
            token_info = response.json()
            self.access_token = token_info["access_token"]
            
            # Set expiration time (subtract 5 minutes for safety)
            expires_in = token_info.get("expires_in", 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
            
            print(f"[OK] SharePoint access token obtained, expires at {self.token_expires_at}")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to get SharePoint access token: {e}")
            raise e
    
    def get_sharepoint_token(self) -> str:
        """Get a token specifically for SharePoint REST API (not Graph API)."""
        # For SharePoint REST API, we'll use the same token
        # The Sites.Read.All permission works for both Graph and SharePoint REST API
        # The token just needs to be formatted correctly for SharePoint
        
        # Return the same token (it should work for both)
        return self.get_access_token()
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def test_connection(self) -> bool:
        """Test SharePoint API connection."""
        try:
            # Test with Microsoft Graph API - use the site hostname format
            headers = self.get_headers()
            
            # Get the site hostname from environment
            site_url = os.getenv("SHAREPOINT_SITE_URL", "https://cloudfuzecom.sharepoint.com/sites/DOC360")
            
            # Extract the site identifier from URL
            # Format: sites/{hostname}:{server-relative-path}
            if ".sharepoint.com/sites/" in site_url:
                # Parse the URL
                parts = site_url.replace("https://", "").replace("http://", "")
                hostname = parts.split("/")[0]  # cloudfuzecom.sharepoint.com
                site_path = "/" + "/".join(parts.split("/")[1:])  # /sites/DOC360
                
                # Use the correct Graph API format
                test_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
            else:
                # Fallback to direct URL format
                test_url = f"https://graph.microsoft.com/v1.0/sites/{site_url}"
            
            print(f"[*] Testing SharePoint connection: {test_url}")
            response = requests.get(test_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("[OK] SharePoint API connection successful")
                return True
            else:
                print(f"[ERROR] SharePoint API test failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"[ERROR] SharePoint connection test failed: {e}")
            return False

# Global authenticator instance (lazy initialization)
_sharepoint_auth_instance = None

def get_sharepoint_auth():
    """Get or create the global SharePoint authenticator instance (lazy initialization)."""
    global _sharepoint_auth_instance
    if _sharepoint_auth_instance is None:
        _sharepoint_auth_instance = SharePointAuthenticator()
    return _sharepoint_auth_instance

# For backward compatibility, create a property-like accessor
class _SharePointAuthProxy:
    """Proxy class to maintain backward compatibility with direct sharepoint_auth access."""
    def __getattr__(self, name):
        return getattr(get_sharepoint_auth(), name)
    
    def __call__(self, *args, **kwargs):
        return get_sharepoint_auth()(*args, **kwargs)

sharepoint_auth = _SharePointAuthProxy()
