# -*- coding: utf-8 -*-
"""
Teams data access layer: reads from MongoDB (teams + user_activity) with fallback to TEAMS_STRUCTURE.
Single source of truth for membership is user_activity.team_name; teams collection holds only metadata.
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Lazy-initialized sync MongoDB client and cache
_client = None
_teams_cache: Optional[Dict[str, dict]] = None
_use_fallback = True


def _get_client():
    """Get sync pymongo client (lazy init)."""
    global _client
    if _client is None:
        try:
            from pymongo import MongoClient
            from config import MONGODB_URL, MONGODB_DATABASE
            _client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            logger.info("[TEAMS_REPO] Connected to MongoDB for teams")
        except Exception as e:
            logger.warning(f"[TEAMS_REPO] MongoDB not available, using fallback: {e}")
            _client = False  # mark as attempted
    return _client if _client else None


def _get_db():
    """Get database; None if not connected."""
    client = _get_client()
    if not client:
        return None
    from config import MONGODB_DATABASE
    return client[MONGODB_DATABASE]


def get_teams_collection():
    """Return MongoDB teams collection or None."""
    db = _get_db()
    return db["teams"] if db is not None else None


def _load_teams_from_mongodb() -> Optional[Dict[str, dict]]:
    """Load team metadata from MongoDB (no members). Returns None if empty or error."""
    coll = get_teams_collection()
    if coll is None:
        return None
    try:
        cursor = coll.find({})
        docs = list(cursor)
        if not docs:
            return None
        result = {}
        for d in docs:
            name = d.get("team_name")
            if not name:
                continue
            result[name] = {
                "lead": d.get("lead", ""),
                "lead_email": d.get("lead_email", ""),
                "color": d.get("color", "#6B7280"),
                "description": d.get("description", ""),
            }
        return result if result else None
    except Exception as e:
        logger.warning(f"[TEAMS_REPO] Failed to load teams from MongoDB: {e}")
        return None


def _get_user_activity_collection():
    """Return user_activity collection or None."""
    db = _get_db()
    return db["user_activity"] if db is not None else None


def get_all_teams() -> Dict[str, dict]:
    """Get all teams. Uses MongoDB if available and populated; else fallback to TEAMS_STRUCTURE.
    Returned shape includes optional 'members' computed from user_activity for backward compatibility.
    """
    teams_meta = _load_teams_from_mongodb()
    if teams_meta is None:
        from app.models.teams import TEAMS_STRUCTURE
        return TEAMS_STRUCTURE
    # Optionally attach members from user_activity for backward-compatible shape
    ua = _get_user_activity_collection()
    if ua is not None:
        try:
            pipeline = [
                {"$match": {"team_name": {"$exists": True, "$ne": ""}, "is_active": {"$ne": False}}},
                {"$group": {"_id": "$team_name", "emails": {"$push": "$user_email"}}}
            ]
            agg = list(ua.aggregate(pipeline))
            team_to_emails = {x["_id"]: x.get("emails", []) for x in agg}
        except Exception as e:
            logger.debug(f"[TEAMS_REPO] Aggregate members: {e}")
            team_to_emails = {}
    else:
        team_to_emails = {}
    result = {}
    for team_name, meta in teams_meta.items():
        out = dict(meta)
        emails = [e for e in team_to_emails.get(team_name, []) if e]
        out["members"] = [{"name": "", "email": e} for e in emails]
        result[team_name] = out
    if not result:
        from app.models.teams import TEAMS_STRUCTURE
        return TEAMS_STRUCTURE
    return result


def get_team_by_name(team_name: str) -> Optional[dict]:
    """Get a specific team by name."""
    teams = get_all_teams()
    return teams.get(team_name)


def get_team_by_member_email(email: str) -> str:
    """Find which team a member belongs to by email. Source of truth: user_activity.team_name."""
    if not email:
        return "Unassigned"
    email_lower = str(email).lower().strip()
    ua = _get_user_activity_collection()
    if ua is not None:
        try:
            doc = ua.find_one({
                "$or": [{"user_email": email_lower}, {"user_id": email_lower}],
                "team_name": {"$exists": True, "$ne": ""},
                "is_active": {"$ne": False}
            }, projection={"team_name": 1})
            if doc and doc.get("team_name"):
                return doc["team_name"]
        except Exception as e:
            logger.debug(f"[TEAMS_REPO] get_team_by_member_email: {e}")
    # Fallback: TEAMS_STRUCTURE
    from app.models.teams import TEAMS_STRUCTURE
    for team_name, team_info in TEAMS_STRUCTURE.items():
        if team_info.get("lead_email", "").lower().strip() == email_lower:
            return team_name
        for member in team_info.get("members", []):
            if (member.get("email") or "").lower().strip() == email_lower:
                return team_name
    return "Unassigned"


def get_all_team_members_emails() -> Dict[str, List[str]]:
    """All emails by team. Derived from user_activity."""
    ua = _get_user_activity_collection()
    if ua is not None:
        try:
            pipeline = [
                {"$match": {"team_name": {"$exists": True, "$ne": ""}, "is_active": {"$ne": False}}},
                {"$group": {"_id": "$team_name", "emails": {"$push": "$user_email"}}}
            ]
            agg = list(ua.aggregate(pipeline))
            return {x["_id"]: [e for e in x.get("emails", []) if e] for x in agg}
        except Exception as e:
            logger.debug(f"[TEAMS_REPO] get_all_team_members_emails: {e}")
    # Fallback
    from app.models.teams import TEAMS_STRUCTURE
    result = {}
    for team_name, team_info in TEAMS_STRUCTURE.items():
        emails = []
        if team_info.get("lead_email"):
            emails.append(team_info["lead_email"].lower())
        for m in team_info.get("members", []):
            e = (m.get("email") or "").lower()
            if e:
                emails.append(e)
        result[team_name] = emails
    return result


def get_team_member_count(team_name: str) -> int:
    """Total members in a team (from user_activity)."""
    ua = _get_user_activity_collection()
    if ua is not None:
        try:
            n = ua.count_documents({"team_name": team_name, "is_active": {"$ne": False}})
            return n
        except Exception as e:
            logger.debug(f"[TEAMS_REPO] get_team_member_count: {e}")
    team = get_team_by_name(team_name)
    if not team:
        return 0
    return len(team.get("members", [])) + (1 if team.get("lead_email") else 0)


def get_team_color(team_name: str) -> str:
    """Color code for a team."""
    team = get_team_by_name(team_name)
    return (team.get("color", "#6B7280") if team else "#6B7280")
