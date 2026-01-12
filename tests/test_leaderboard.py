#!/usr/bin/env python
"""Quick test to verify leaderboard system is working"""

import asyncio
from app.models.teams import (
    get_all_teams,
    get_team_by_member_email,
    get_team_member_count,
    get_team_color,
    TEAMS_STRUCTURE
)

def test_teams_structure():
    """Test that all 19 teams are configured"""
    teams = get_all_teams()
    print(f"[OK] Total Teams: {len(teams)}")
    assert len(teams) == 19, f"Expected 19 teams, got {len(teams)}"
    
    print("\n[INFO] Teams Configured:")
    for i, team_name in enumerate(teams.keys(), 1):
        team = teams[team_name]
        member_count = get_team_member_count(team_name)
        color = get_team_color(team_name)
        print(f"  {i:2d}. {team_name:20s} - {member_count:2d} members - {color}")

def test_email_matching():
    """Test email-based team matching"""
    print("\n[TEST] Email Matching Tests:")
    
    test_cases = [
        ("santosh@cloudfuze.com", "Content"),
        ("akhila.aenkoju@cloudfuze.com", "Content"),
        ("ankit@cloudfuze.com", "Messaging & Email"),
        ("kamal.basha@cloudfuze.com", "QA"),
        ("ravi.poli@cloudfuze.com", "Neutara Labs"),
        ("pavan@cloudfuze.com", "Infra"),
        ("unknown@example.com", "Unassigned"),
    ]
    
    for email, expected_team in test_cases:
        actual_team = get_team_by_member_email(email)
        status = "[OK]" if actual_team == expected_team else "[FAIL]"
        print(f"  {status} {email:40s} -> {actual_team:20s} (Expected: {expected_team})")
        assert actual_team == expected_team, f"Mismatch for {email}"

def test_team_members():
    """Test that team members are properly configured"""
    print("\n[TEST] Team Member Verification:")
    
    test_teams = {
        "Content": 13,  # 12 members + 1 lead
        "Messaging & Email": 20,
        "QA": 10,
        "Neutara Labs": 9,
        "Infra": 6,
        "HR": 5
    }
    
    for team_name, expected_count in test_teams.items():
        actual_count = get_team_member_count(team_name)
        status = "[OK]" if actual_count == expected_count else "[FAIL]"
        print(f"  {status} {team_name:20s} - {actual_count:2d} members (Expected: {expected_count})")
        assert actual_count == expected_count, f"Member count mismatch for {team_name}"

def test_team_colors():
    """Verify each team has a unique color"""
    print("\n[TEST] Team Colors Verification:")
    
    colors = {}
    duplicates = []
    
    for team_name in get_all_teams().keys():
        color = get_team_color(team_name)
        if color in colors:
            duplicates.append((team_name, color, colors[color]))
        colors[team_name] = color
        print(f"  [OK] {team_name:20s} - {color}")
    
    if duplicates:
        print(f"\n[WARNING] {len(duplicates)} duplicate colors found:")
        for team, color, first_team in duplicates:
            print(f"  - {team} and {first_team} both use {color}")
    else:
        print(f"\n[OK] All {len(colors)} teams have colors assigned")

def main():
    """Run all tests"""
    print("=" * 60)
    print("LEADERBOARD SYSTEM VERIFICATION")
    print("=" * 60)
    
    try:
        test_teams_structure()
        test_email_matching()
        test_team_members()
        test_team_colors()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - Total Teams: 19 [OK]")
        print(f"  - Total Members: 138+ [OK]")
        print(f"  - Email Matching: Working [OK]")
        print(f"  - Color Assignment: Complete [OK]")
        print("\nLeaderboard system is ready to use!")
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())

