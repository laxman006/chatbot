# -*- coding: utf-8 -*-
"""
Cloud API Research MongoDB Models

Models and database operations for storing cloud API research results.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from config import MONGODB_URL, MONGODB_DATABASE
import logging

logger = logging.getLogger(__name__)


class CloudResearchStore:
    """MongoDB storage for cloud API research results"""
    
    def __init__(self):
        """Initialize MongoDB connection"""
        self.client = MongoClient(MONGODB_URL)
        self.db = self.client[MONGODB_DATABASE]
        self.collection: Collection = self.db["cloud_api_research"]
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create necessary indexes for efficient queries"""
        try:
            # Index on cloud name (unique)
            self.collection.create_index([("cloud_name", ASCENDING)], unique=True)
            
            # Index on last_researched for cache invalidation
            self.collection.create_index([("last_researched", DESCENDING)])
            
            # Index on created_by for tracking
            self.collection.create_index([("created_by", ASCENDING)])
            
            # Index on confidence_score for quality filtering
            self.collection.create_index([("confidence_score", DESCENDING)])
            
            logger.info("[OK] Cloud research indexes created")
        except Exception as e:
            logger.warning(f"[WARN] Could not create indexes: {e}")
    
    def save_research(self, research_data: Dict) -> bool:
        """
        Save or update cloud API research results.
        
        Args:
            research_data: Complete research data for a cloud
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cloud_name = research_data.get("cloud_name")
            if not cloud_name:
                logger.error("No cloud_name provided in research data")
                return False
            
            # Add metadata
            research_data["last_researched"] = datetime.now(timezone.utc).isoformat()
            
            # Remove _version from research_data to avoid conflict
            research_data.pop("_version", None)
            
            # Check if document exists to handle versioning correctly
            existing = self.collection.find_one({"cloud_name": cloud_name})
            
            if existing:
                # Update existing document
                result = self.collection.update_one(
                    {"cloud_name": cloud_name},
                    {
                        "$set": research_data,
                        "$inc": {"_version": 1}
                    }
                )
            else:
                # Insert new document with version 1
                research_data["_version"] = 1
                result = self.collection.insert_one(research_data)
                research_data.pop("_version")  # Remove for return consistency
            
            logger.info(f"[OK] Saved research for {cloud_name}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to save research: {e}")
            return False
    
    def get_research(self, cloud_name: str) -> Optional[Dict]:
        """
        Get research results for a specific cloud.
        
        Args:
            cloud_name: Name of the cloud (case-insensitive)
            
        Returns:
            Research data dict or None if not found
        """
        try:
            # Case-insensitive search
            result = self.collection.find_one(
                {"cloud_name": {"$regex": f"^{cloud_name}$", "$options": "i"}}
            )
            
            if result:
                # Remove MongoDB _id from result
                result.pop("_id", None)
                logger.info(f"[OK] Retrieved research for {cloud_name}")
                return result
            else:
                logger.info(f"[INFO] No research found for {cloud_name}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to get research: {e}")
            return None
    
    def list_all_clouds(self, limit: int = 100) -> List[Dict]:
        """
        List all researched clouds with basic info.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of cloud summaries
        """
        try:
            cursor = self.collection.find(
                {},
                {
                    "cloud_name": 1,
                    "display_name": 1,
                    "last_researched": 1,
                    "confidence_score": 1,
                    "scim_support.enabled": 1,
                    "core_operations": 1,
                    "created_by": 1,
                    "_id": 0
                }
            ).sort("last_researched", DESCENDING).limit(limit)
            
            results = []
            for doc in cursor:
                # Calculate operation counts
                core_count = 0
                if "core_operations" in doc:
                    for category in doc["core_operations"].values():
                        core_count += len(category)
                
                results.append({
                    "cloud_name": doc.get("cloud_name"),
                    "display_name": doc.get("display_name", doc.get("cloud_name")),
                    "last_researched": doc.get("last_researched"),
                    "confidence_score": doc.get("confidence_score", 0),
                    "scim_enabled": doc.get("scim_support", {}).get("enabled", False),
                    "core_operations_count": core_count,
                    "created_by": doc.get("created_by", "unknown"),
                })
            
            logger.info(f"[OK] Listed {len(results)} clouds")
            return results
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to list clouds: {e}")
            return []
    
    def delete_research(self, cloud_name: str) -> bool:
        """
        Delete research results for a cloud.
        
        Args:
            cloud_name: Name of the cloud
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            result = self.collection.delete_one(
                {"cloud_name": {"$regex": f"^{cloud_name}$", "$options": "i"}}
            )
            
            if result.deleted_count > 0:
                logger.info(f"[OK] Deleted research for {cloud_name}")
                return True
            else:
                logger.info(f"[INFO] No research found to delete for {cloud_name}")
                return False
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete research: {e}")
            return False
    
    def is_cache_valid(self, cloud_name: str, cache_days: int = 30) -> bool:
        """
        Check if cached research is still valid.
        
        Args:
            cloud_name: Name of the cloud
            cache_days: Number of days before cache expires
            
        Returns:
            True if cache is valid, False if expired or not found
        """
        try:
            research = self.get_research(cloud_name)
            if not research:
                return False
            
            last_researched_str = research.get("last_researched")
            if not last_researched_str:
                return False
            
            last_researched = datetime.fromisoformat(last_researched_str.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - last_researched
            
            is_valid = age.days < cache_days
            logger.info(f"[INFO] Cache for {cloud_name} is {'valid' if is_valid else 'expired'} (age: {age.days} days)")
            return is_valid
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to check cache validity: {e}")
            return False
    
    def search_clouds(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for clouds by name (fuzzy search).
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching clouds
        """
        try:
            cursor = self.collection.find(
                {
                    "$or": [
                        {"cloud_name": {"$regex": query, "$options": "i"}},
                        {"display_name": {"$regex": query, "$options": "i"}},
                    ]
                },
                {
                    "cloud_name": 1,
                    "display_name": 1,
                    "last_researched": 1,
                    "confidence_score": 1,
                    "_id": 0
                }
            ).limit(limit)
            
            results = list(cursor)
            logger.info(f"[OK] Found {len(results)} clouds matching '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to search clouds: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """
        Get overall statistics about researched clouds.
        
        Returns:
            Statistics dict
        """
        try:
            total_clouds = self.collection.count_documents({})
            
            # Count clouds with SCIM support
            scim_enabled = self.collection.count_documents({"scim_support.enabled": True})
            
            # Get average confidence score
            pipeline = [
                {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence_score"}}}
            ]
            avg_result = list(self.collection.aggregate(pipeline))
            avg_confidence = avg_result[0]["avg_confidence"] if avg_result else 0
            
            # Get most recent research
            recent = self.collection.find_one(
                {},
                {"cloud_name": 1, "last_researched": 1, "_id": 0},
                sort=[("last_researched", DESCENDING)]
            )
            
            return {
                "total_clouds_researched": total_clouds,
                "clouds_with_scim": scim_enabled,
                "average_confidence_score": round(avg_confidence, 2),
                "most_recent_research": recent,
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to get statistics: {e}")
            return {}


# Global instance
cloud_research_store = CloudResearchStore()


# Helper functions for easy access
def save_cloud_research(research_data: Dict) -> bool:
    """Save cloud research results"""
    return cloud_research_store.save_research(research_data)


def get_cloud_research(cloud_name: str) -> Optional[Dict]:
    """Get cloud research results"""
    return cloud_research_store.get_research(cloud_name)


def list_researched_clouds(limit: int = 100) -> List[Dict]:
    """List all researched clouds"""
    return cloud_research_store.list_all_clouds(limit)


def delete_cloud_research(cloud_name: str) -> bool:
    """Delete cloud research"""
    return cloud_research_store.delete_research(cloud_name)


def is_research_cached(cloud_name: str, cache_days: int = 30) -> bool:
    """Check if research is cached and valid"""
    return cloud_research_store.is_cache_valid(cloud_name, cache_days)


def search_researched_clouds(query: str, limit: int = 10) -> List[Dict]:
    """Search for researched clouds"""
    return cloud_research_store.search_clouds(query, limit)


def get_research_statistics() -> Dict:
    """Get overall research statistics"""
    return cloud_research_store.get_statistics()
