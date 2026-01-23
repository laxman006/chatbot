# -*- coding: utf-8 -*-
"""
Jira Configuration Service - Handles config storage and encryption
"""
import os
import json
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional, Dict, Any
from datetime import datetime


class JiraConfigService:
    """Service for managing Jira configuration with encryption."""
    
    def __init__(self):
        self.config_file = "./data/jira_config.json"
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        Path("./data").mkdir(parents=True, exist_ok=True)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key."""
        key_file = "./data/.jira_encryption_key"
        
        # Try to get from environment first (for production)
        env_key = os.getenv("JIRA_ENCRYPTION_KEY")
        if env_key:
            return env_key.encode()
        
        # Otherwise, use file-based key
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            print(f"[OK] Generated new encryption key: {key_file}")
            return key
    
    def encrypt_token(self, token: str) -> str:
        """Encrypt API token."""
        if not token:
            return ""
        return self.fernet.encrypt(token.encode()).decode()
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt API token."""
        if not encrypted_token:
            return ""
        try:
            return self.fernet.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            print(f"[ERROR] Failed to decrypt token: {e}")
            return ""
    
    def mask_token(self, token: str) -> str:
        """Mask token for display (show only last 4 chars)."""
        if not token or len(token) < 4:
            return "****"
        return f"****{token[-4:]}"
    
    def save_config(self, config_data: Dict[str, Any]) -> bool:
        """Save configuration to file (encrypts token)."""
        try:
            # Encrypt the API token
            if 'api_token' in config_data and config_data['api_token']:
                config_data['api_token'] = self.encrypt_token(config_data['api_token'])
            
            # Add metadata
            config_data['last_updated'] = datetime.now().isoformat()
            config_data['version'] = '1.0'
            
            # Save to file
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            print(f"[OK] Saved Jira configuration to {self.config_file}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")
            return False
    
    def load_config(self, decrypt_token: bool = False) -> Optional[Dict[str, Any]]:
        """Load configuration from file."""
        if not os.path.exists(self.config_file):
            return None
        
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            # Decrypt token if requested
            if decrypt_token and 'api_token' in config_data:
                config_data['api_token'] = self.decrypt_token(config_data['api_token'])
            
            return config_data
        except Exception as e:
            print(f"[ERROR] Failed to load config: {e}")
            return None
    
    def test_connection(self, server: str, email: str, api_token: str) -> Dict[str, Any]:
        """Test Jira connection with provided credentials."""
        try:
            from jira import JIRA
            
            # Try to connect
            jira = JIRA(
                server=server,
                basic_auth=(email, api_token)
            )
            
            # Get current user
            current_user = jira.current_user()
            
            return {
                "success": True,
                "message": f"Connected successfully as {current_user}",
                "user": current_user,
                "server": server
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
                "error": str(e)
            }
    
    def get_masked_config(self) -> Optional[Dict[str, Any]]:
        """Get configuration with masked token."""
        config = self.load_config(decrypt_token=False)
        if not config:
            return None
        
        # Mask the token
        if 'api_token' in config:
            # For encrypted token, we need to decrypt first to mask properly
            decrypted = self.decrypt_token(config['api_token'])
            config['api_token_masked'] = self.mask_token(decrypted)
            del config['api_token']  # Remove encrypted token from response
        
        return config
    
    def update_env_file(self, config_data: Dict[str, Any]):
        """Update .env file with new configuration."""
        # Note: This is optional - config file is the primary storage
        # You can implement .env file updates here if needed
        pass
