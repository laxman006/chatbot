#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test backend team endpoint directly without auth to debug
"""

import asyncio
from app.langfuse_integration import langfuse_client
from app.models.teams import TEAMS_STRUCTURE, TEAMS
import json

async def test_backend():
    print("[INFO] Testing backend logic directly\n")
    
    # Check if Langfuse client is initialized
    print(f"[1] Langfuse client initialized: {langfuse_client is not None}")
    
    # Check if TEAMS structure is correct
    print(f"\n[2] TEAMS_STRUCTURE has {len(TEAMS_STRUCTURE)} teams:")
    for team_name, team_info in TEAMS_STRUCTURE.items():
        lead = team_info.get("lead")
        members_count = len(team_info.get("members", []))
        print(f"   - {team_name}: {members_count} members, Lead: {lead}")
    
    # Check backward compatibility TEAMS
    print(f"\n[3] TEAMS (legacy format) has {len(TEAMS)} teams:")
    for team_name, team_info in TEAMS.items():
        lead = team_info.get("Lead")
        members = team_info.get("Members", [])
        members_count = len([m for m in members if m])
        print(f"   - {team_name}: {members_count} members, Lead: {lead}")
        if members:
            print(f"      First member: {members[0]}")

if __name__ == "__main__":
    asyncio.run(test_backend())

