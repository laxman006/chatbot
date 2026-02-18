#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-time migration: seed MongoDB `teams` collection from TEAMS_STRUCTURE (metadata only, no members).
Create indexes for teams, user_activity, and audit_logs.
Optional: backfill user_activity.team_name from TEAMS_STRUCTURE for users with no team.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from pymongo.errors import PyMongoError


def get_config():
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DATABASE", "slack2teams")
    return url, db_name


def create_indexes(db):
    """Create indexes for teams, user_activity, audit_logs (idempotent)."""
    # teams: team_name unique
    db["teams"].create_index("team_name", unique=True)
    # user_activity: user_email, team_name, is_active (for aggregation)
    db["user_activity"].create_index("user_email")
    db["user_activity"].create_index("team_name")
    db["user_activity"].create_index("is_active")
    # audit_logs: created_at (for Phase 3; creates collection if missing)
    db["audit_logs"].create_index("created_at")
    print("[OK] Indexes created/verified")


def migrate_teams(db):
    """Seed teams collection from TEAMS_STRUCTURE (metadata only)."""
    from app.models.teams import TEAMS_STRUCTURE
    coll = db["teams"]
    inserted, updated = 0, 0
    for team_name, info in TEAMS_STRUCTURE.items():
        doc = {
            "team_name": team_name,
            "lead": info.get("lead", ""),
            "lead_email": info.get("lead_email", ""),
            "color": info.get("color", "#6B7280"),
            "description": info.get("description", ""),
        }
        r = coll.update_one(
            {"team_name": team_name},
            {"$set": doc},
            upsert=True
        )
        if r.upserted_id:
            inserted += 1
        elif r.modified_count:
            updated += 1
    total = len(TEAMS_STRUCTURE)
    print(f"[OK] Teams: {inserted} inserted, {updated} updated, {total} total")
    return total


def backfill_user_activity_team(db):
    """Optional: set user_activity.team_name for users who have none, using TEAMS_STRUCTURE."""
    from app.models.teams import TEAMS_STRUCTURE
    ua = db["user_activity"]
    # Build email -> team_name from TEAMS_STRUCTURE
    email_to_team = {}
    for team_name, info in TEAMS_STRUCTURE.items():
        lead_email = (info.get("lead_email") or "").lower().strip()
        if lead_email:
            email_to_team[lead_email] = team_name
        for m in info.get("members", []):
            e = (m.get("email") or "").lower().strip()
            if e:
                email_to_team[e] = team_name
    # Find user_activity docs with no team_name
    cursor = ua.find({"$or": [{"team_name": {"$exists": False}}, {"team_name": ""}, {"team_name": None}]})
    updated = 0
    for doc in cursor:
        user_id = doc.get("user_id", "")
        user_email = (doc.get("user_email") or user_id or "").lower().strip()
        if not user_email:
            continue
        team_name = email_to_team.get(user_email)
        if not team_name:
            continue
        info = TEAMS_STRUCTURE.get(team_name, {})
        manager_email = info.get("lead_email", "") or ""
        manager_name = info.get("lead", "") or ""
        ua.update_one(
            {"_id": doc["_id"]},
            {"$set": {"team_name": team_name, "manager_email": manager_email, "manager_name": manager_name}}
        )
        updated += 1
    print(f"[OK] user_activity backfill: {updated} documents updated")
    return updated


def backfill_is_active(db):
    """Set is_active=True for all user_activity docs that don't have it (idempotent)."""
    ua = db["user_activity"]
    r = ua.update_many(
        {"is_active": {"$exists": False}},
        {"$set": {"is_active": True}}
    )
    print(f"[OK] user_activity is_active backfill: {r.modified_count} documents updated")
    return r.modified_count


def main():
    url, db_name = get_config()
    print(f"Connecting to {db_name}...")
    try:
        client = MongoClient(url, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        db = client[db_name]
    except PyMongoError as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        sys.exit(1)
    create_indexes(db)
    migrate_teams(db)
    backfill_user_activity_team(db)
    backfill_is_active(db)
    print("Migration complete.")


if __name__ == "__main__":
    main()
