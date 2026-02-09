"""
Weaviate client wrapper for connection management and health checks.

Provides a singleton client instance with retry logic and health monitoring.
Uses Weaviate Python Client v4 API.
"""

import os
import logging
from typing import Optional
import weaviate
from weaviate.classes.config import Configure, Property, DataType
from config import WEAVIATE_URL, WEAVIATE_API_KEY

logger = logging.getLogger(__name__)

# Global client instance
_weaviate_client: Optional[weaviate.WeaviateClient] = None


def get_weaviate_client() -> Optional[weaviate.WeaviateClient]:
    """
    Get or create Weaviate client instance (singleton pattern).
    Auto-reconnects if client was closed.
    
    Returns:
        Weaviate client instance or None if connection fails
    """
    global _weaviate_client
    
    # Check if client exists and try to use it
    if _weaviate_client is not None:
        try:
            # Try to check if client is ready (this will fail if closed)
            if _weaviate_client.is_ready():
                return _weaviate_client
            else:
                # Client exists but not ready, reset and reconnect
                logger.info("[WEAVIATE] Client not ready, reconnecting...")
                _weaviate_client = None
        except Exception as e:
            # If check fails (e.g., client was closed), reset and reconnect
            logger.info(f"[WEAVIATE] Client check failed ({e}), reconnecting...")
            _weaviate_client = None
    
    try:
        # Determine connection method based on URL
        if WEAVIATE_URL.startswith("http://localhost") or WEAVIATE_URL.startswith("http://127.0.0.1"):
            # Local connection
            connection_params = {
                "host": WEAVIATE_URL.replace("http://", "").split(":")[0],
                "port": int(WEAVIATE_URL.split(":")[-1]) if ":" in WEAVIATE_URL else 8080,
            }
            
            # Add auth if API key provided
            if WEAVIATE_API_KEY:
                connection_params["auth_credentials"] = weaviate.classes.init.Auth.api_key(WEAVIATE_API_KEY)
            
            _weaviate_client = weaviate.connect_to_local(**connection_params)
        else:
            # Custom/cloud connection (parse URL to http_host and http_port)
            # Parse URL like http://weaviate:8080 or https://cloud.weaviate.io
            is_https = WEAVIATE_URL.startswith("https://")
            url_clean = WEAVIATE_URL.replace("http://", "").replace("https://", "")
            url_parts = url_clean.split(":")
            host = url_parts[0]
            http_port = int(url_parts[1]) if len(url_parts) > 1 else (443 if is_https else 8080)
            # Weaviate default gRPC port is 50051 (must be different from HTTP port)
            grpc_port = 50051
            
            connection_params = {
                "http_host": host,
                "http_port": http_port,
                "http_secure": is_https,
                # gRPC uses different port (50051 is Weaviate default)
                "grpc_host": host,
                "grpc_port": grpc_port,
                "grpc_secure": is_https,
            }
            
            # Add auth if API key provided
            if WEAVIATE_API_KEY:
                connection_params["auth_credentials"] = weaviate.classes.init.Auth.api_key(WEAVIATE_API_KEY)
            
            # Add additional headers for OpenAI embeddings if needed
            additional_headers = {}
            if os.getenv("OPENAI_API_KEY"):
                additional_headers["X-OpenAI-Api-Key"] = os.getenv("OPENAI_API_KEY")
            
            if additional_headers:
                connection_params["headers"] = additional_headers
            
            _weaviate_client = weaviate.connect_to_custom(**connection_params)
        
        # Test connection
        if not _weaviate_client.is_ready():
            logger.error(f"[WEAVIATE] Connection failed: Weaviate at {WEAVIATE_URL} is not ready")
            _weaviate_client = None
            return None
        
        logger.info(f"[WEAVIATE] ✓ Connected to Weaviate at {WEAVIATE_URL}")
        return _weaviate_client
        
    except Exception as e:
        logger.error(f"[WEAVIATE] Failed to connect to Weaviate: {e}")
        import traceback
        traceback.print_exc()
        _weaviate_client = None
        return None


def check_weaviate_health() -> bool:
    """
    Check if Weaviate is healthy and ready.
    
    Returns:
        True if Weaviate is healthy, False otherwise
    """
    try:
        client = get_weaviate_client()
        if client is None:
            return False
        
        # Check if Weaviate is ready
        if not client.is_ready():
            logger.warning("[WEAVIATE] Health check failed: Weaviate is not ready")
            return False
        
        # Check if Weaviate is live
        if not client.is_live():
            logger.warning("[WEAVIATE] Health check failed: Weaviate is not live")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"[WEAVIATE] Health check error: {e}")
        return False


def reset_weaviate_client():
    """
    Reset the global Weaviate client instance.
    Useful for testing or reconnection scenarios.
    """
    global _weaviate_client
    if _weaviate_client is not None:
        try:
            _weaviate_client.close()
        except:
            pass
    _weaviate_client = None
    logger.info("[WEAVIATE] Client instance reset")


def get_weaviate_meta() -> Optional[dict]:
    """
    Get Weaviate meta information.
    
    Returns:
        Dictionary with Weaviate version and info, or None if unavailable
    """
    try:
        client = get_weaviate_client()
        if client is None:
            return None
        
        # In v4 API, meta is accessed differently
        # We can get version info from the client
        return {
            "version": "v4",
            "url": WEAVIATE_URL,
        }
        
    except Exception as e:
        logger.error(f"[WEAVIATE] Failed to get meta: {e}")
        return None
