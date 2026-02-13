# -*- coding: utf-8 -*-
"""
Cloud Classification System

Classifies cloud services by type to set appropriate expectations
for Manage Team API availability.
"""

import logging
from typing import Dict, Tuple, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class CloudCategory(str, Enum):
    """Cloud service categories"""
    IAM_DIRECTORY = "IAM / Directory SaaS"
    COLLABORATION = "Collaboration SaaS"
    BUSINESS_APP = "Business Application SaaS"
    DEVELOPER_PLATFORM = "Developer Platform"
    CONTENT_MANAGEMENT = "Content Management Platform"
    UNKNOWN = "Unknown"


class ManageTeamSupport(str, Enum):
    """Expected Manage Team API support levels"""
    FULL = "full"  # Expected to have all 8 operations
    PARTIAL = "partial"  # May have some operations
    LIMITED = "limited"  # Unlikely to have lifecycle APIs
    NONE = "none"  # Definitely no Manage Team APIs


# Known cloud classifications (for speed and accuracy)
KNOWN_CLASSIFICATIONS = {
    # IAM / Directory Platforms (FULL Support Expected)
    "okta": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "azure ad": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "azure active directory": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "google workspace": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "onelogin": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "auth0": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    "jumpcloud": (CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL),
    
    # Content Management (FULL Support Expected)
    "box": (CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL),
    "dropbox": (CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL),
    "onedrive": (CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL),
    "google drive": (CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL),
    "sharepoint": (CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL),
    
    # Collaboration Platforms (PARTIAL Support)
    "slack": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "microsoft teams": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "zoom": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "webex": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "jira": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "confluence": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    "atlassian": (CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL),
    
    # Developer Platforms (PARTIAL Support)
    "github": (CloudCategory.DEVELOPER_PLATFORM, ManageTeamSupport.PARTIAL),
    "gitlab": (CloudCategory.DEVELOPER_PLATFORM, ManageTeamSupport.PARTIAL),
    "bitbucket": (CloudCategory.DEVELOPER_PLATFORM, ManageTeamSupport.PARTIAL),
    
    # Business Applications (LIMITED/NONE Support)
    "canny": (CloudCategory.BUSINESS_APP, ManageTeamSupport.NONE),
    "notion": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "trello": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "asana": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "monday": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "airtable": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "clickup": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "linear": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "figma": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
    "miro": (CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED),
}


class CloudClassifier:
    """Classifies cloud services by type and expected capabilities"""
    
    def classify(self, cloud_name: str, extracted_data: Optional[Dict] = None) -> Dict:
        """
        Classify a cloud service.
        
        Args:
            cloud_name: Name of the cloud
            extracted_data: Optional extracted data for heuristic classification
            
        Returns:
            Classification dict with category, support level, and reasoning
        """
        cloud_key = cloud_name.lower().strip()
        
        # Check known classifications first
        if cloud_key in KNOWN_CLASSIFICATIONS:
            category, support = KNOWN_CLASSIFICATIONS[cloud_key]
            logger.info(f"[CLASSIFIER] {cloud_name} → {category.value} (Known)")
            
            return {
                "category": category.value,
                "manage_team_support": support.value,
                "confidence": 0.95,
                "reasoning": f"Known classification: {category.value}",
                "expected_coverage": self._get_expected_coverage(support)
            }
        
        # Heuristic classification for unknown clouds
        logger.info(f"[CLASSIFIER] {cloud_name} is unknown, using heuristic classification")
        category, support = self._heuristic_classify(cloud_name, extracted_data)
        
        return {
            "category": category.value,
            "manage_team_support": support.value,
            "confidence": 0.60,  # Lower confidence for heuristic
            "reasoning": f"Heuristic classification: {category.value}",
            "expected_coverage": self._get_expected_coverage(support)
        }
    
    def _heuristic_classify(self, cloud_name: str, extracted_data: Optional[Dict]) -> Tuple[CloudCategory, ManageTeamSupport]:
        """
        Classify cloud using heuristics when not in known list.
        
        Args:
            cloud_name: Cloud name
            extracted_data: Extracted API data (if available)
            
        Returns:
            Tuple of (category, support_level)
        """
        name_lower = cloud_name.lower()
        
        # Check for IAM/Directory keywords
        iam_keywords = ['identity', 'auth', 'sso', 'directory', 'idp', 'iam']
        if any(keyword in name_lower for keyword in iam_keywords):
            return CloudCategory.IAM_DIRECTORY, ManageTeamSupport.FULL
        
        # Check for collaboration keywords
        collab_keywords = ['chat', 'meeting', 'collaboration', 'communicate', 'workspace']
        if any(keyword in name_lower for keyword in collab_keywords):
            return CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL
        
        # Check for developer platform keywords
        dev_keywords = ['git', 'code', 'repository', 'ci', 'cd', 'deploy']
        if any(keyword in name_lower for keyword in dev_keywords):
            return CloudCategory.DEVELOPER_PLATFORM, ManageTeamSupport.PARTIAL
        
        # Check for content management keywords
        content_keywords = ['drive', 'storage', 'files', 'documents', 'share']
        if any(keyword in name_lower for keyword in content_keywords):
            return CloudCategory.CONTENT_MANAGEMENT, ManageTeamSupport.FULL
        
        # If extracted data shows user/group APIs, classify as likely having support
        if extracted_data:
            endpoints = extracted_data.get('api_endpoints', [])
            if endpoints:
                has_user_apis = any('user' in str(ep.get('path', '')).lower() for ep in endpoints)
                has_group_apis = any('group' in str(ep.get('path', '')).lower() for ep in endpoints)
                
                if has_user_apis and has_group_apis:
                    return CloudCategory.COLLABORATION, ManageTeamSupport.PARTIAL
        
        # Default: Business App with limited support
        return CloudCategory.BUSINESS_APP, ManageTeamSupport.LIMITED
    
    def _get_expected_coverage(self, support: ManageTeamSupport) -> str:
        """Get expected coverage range for support level"""
        if support == ManageTeamSupport.FULL:
            return "80-100%"
        elif support == ManageTeamSupport.PARTIAL:
            return "40-70%"
        elif support == ManageTeamSupport.LIMITED:
            return "10-30%"
        else:  # NONE
            return "0-5%"
    
    def should_skip_extraction(self, classification: Dict) -> bool:
        """
        Determine if Manage Team extraction should be skipped for this cloud.
        
        Args:
            classification: Classification dict
            
        Returns:
            True if extraction should be skipped
        """
        support = classification.get("manage_team_support")
        return support == ManageTeamSupport.NONE.value
    
    def interpret_zero_coverage(self, classification: Dict) -> str:
        """
        Interpret what 0% coverage means for this cloud type.
        
        Args:
            classification: Classification dict
            
        Returns:
            Interpretation message
        """
        category = classification.get("category")
        support = classification.get("manage_team_support")
        
        if support == ManageTeamSupport.FULL.value:
            return "⚠️ Unexpected - This cloud type should support Manage Team APIs. Likely an extraction issue."
        elif support == ManageTeamSupport.PARTIAL.value:
            return "⚠️ Possible - This cloud may have limited user/group APIs. Manual verification recommended."
        elif support == ManageTeamSupport.LIMITED.value:
            return "✅ Expected - This cloud type typically has limited or no admin lifecycle APIs."
        else:  # NONE
            return "✅ Expected - This cloud does not provide Manage Team APIs."


def classify_cloud(cloud_name: str, extracted_data: Optional[Dict] = None) -> Dict:
    """
    Convenience function to classify a cloud.
    
    Args:
        cloud_name: Cloud service name
        extracted_data: Optional extracted API data
        
    Returns:
        Classification dict
    """
    classifier = CloudClassifier()
    return classifier.classify(cloud_name, extracted_data)


def get_expected_operations_for_cloud(classification: Dict) -> List[str]:
    """
    Get expected operations based on cloud classification.
    Dynamic expectations per cloud type - NOT fixed 8 operations.
    
    Args:
        classification: Cloud classification dict
        
    Returns:
        List of expected operation names for this cloud type
    """
    support_level = classification.get("manage_team_support")
    category = classification.get("category")
    
    if support_level == ManageTeamSupport.FULL.value:
        # IAM/Directory & Content Management: expect ALL operations
        return [
            "getUsers", "createUser", "updateUser", "deleteUser",
            "getGroups", "getGroupMembers", "addUserToGroup", "removeUserFromGroup"
        ]
    
    elif support_level == ManageTeamSupport.PARTIAL.value:
        # Collaboration & Developer: expect read + basic membership only
        return [
            "getUsers", "getGroups", "getGroupMembers", "addUserToGroup", "removeUserFromGroup"
        ]
    
    elif support_level == ManageTeamSupport.LIMITED.value:
        # Business Apps: expect read-only
        return ["getUsers", "getGroups"]
    
    else:  # NONE
        # No expectations
        return []
