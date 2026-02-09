# -*- coding: utf-8 -*-
"""
Weekly Team Leaderboard Report Generation

Generates HTML email templates and PDF reports for weekly team leaderboard data.
"""

import os
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
from reportlab.lib.utils import ImageReader

from app.models.teams import get_team_by_name, get_team_color, TEAMS_STRUCTURE

logger = logging.getLogger(__name__)

# Dashboard colors matching the frontend
COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#6366f1', '#ef4444', '#14b8a6', '#f97316', '#06b6d4']


async def _get_all_time_team_data(exclude_teams_list: List[str]) -> Dict:
    """
    Get all-time team data from user_activity collection.
    This is the SAME logic as /admin/teams/summary when no dates are provided.
    """
    from app.mongodb_memory import mongodb_memory
    from app.models.teams import (
        get_team_by_name, get_team_color, get_team_by_member_email, TEAMS_STRUCTURE
    )
    
    user_activity_collection = mongodb_memory.database["user_activity"]
    
    # Get all user_activity documents
    cursor = user_activity_collection.find({})
    all_users = await cursor.to_list(length=None)
    
    logger.info(f"[WEEKLY REPORT] Found {len(all_users)} users in user_activity (all-time)")
    
    # Group users by team_name
    teams_data = {}
    skipped_no_team = 0
    skipped_excluded = 0
    
    for user_doc in all_users:
        user_email = user_doc.get("user_email", "").lower()
        user_name = user_doc.get("user_name", "")
        team_name = user_doc.get("team_name")
        total_messages = user_doc.get("total_messages", 0)
        
        # Skip users with no messages
        if total_messages == 0:
            continue
        
        # Fallback to teams.py if team_name not found in user_activity
        if not team_name or team_name.strip() == "":
            team_name = get_team_by_member_email(user_email)
            if team_name == "Unassigned":
                team_name = None
        
        # Skip users without team assignment
        if not team_name or team_name.strip() == "":
            skipped_no_team += 1
            continue
        
        # Skip excluded teams
        if exclude_teams_list and team_name in exclude_teams_list:
            skipped_excluded += 1
            logger.debug(f"[WEEKLY REPORT] Skipping team '{team_name}' - excluded")
            continue
        
        # Initialize team if not exists
        if team_name not in teams_data:
            teams_data[team_name] = {
                "team_name": team_name,
                "total_messages": 0,
                "active_members": set(),
                "member_details": []
            }
        
        # Aggregate team data
        teams_data[team_name]["total_messages"] += total_messages
        teams_data[team_name]["active_members"].add(user_email)
        teams_data[team_name]["member_details"].append({
            "email": user_email,
            "name": user_name,
            "messages": total_messages
        })
    
    # Convert to list format and get team info from teams.py
    teams_list = []
    for team_name, team_data in teams_data.items():
        team_info = get_team_by_name(team_name)
        if not team_info:
            team_info = {
                "lead": None,
                "lead_email": None,
                "members": [],
                "color": "#6B7280",
                "description": team_name
            }
        
        teams_list.append({
            "team_name": team_name,
            "lead": team_info.get("lead"),
            "lead_email": team_info.get("lead_email"),
            "color": get_team_color(team_name) or team_info.get("color", "#6B7280"),
            "description": team_info.get("description", team_name),
            "total_messages": team_data["total_messages"],
            "total_questions": team_data["total_messages"],
            "unique_questions": 0,
            "top_questions": [],
            "active_members_count": len(team_data["active_members"]),
            "member_count": len(team_info.get("members", [])),
            "members": team_data["member_details"]
        })
    
    # Sort by total_messages descending
    teams_list.sort(key=lambda x: x["total_messages"], reverse=True)
    
    logger.info(f"[WEEKLY REPORT] Fetched {len(teams_list)} teams (all-time)")
    logger.info(f"[WEEKLY REPORT] Skipped {skipped_no_team} users (no team), {skipped_excluded} excluded teams")
    if teams_list:
        logger.info(f"[WEEKLY REPORT] Top team: {teams_list[0]['team_name']} with {teams_list[0]['total_messages']} messages")
    
    return {
        "status": "success",
        "total_teams": len(TEAMS_STRUCTURE),
        "teams": teams_list,
        "generated_at": datetime.utcnow().isoformat(),
        "data_source": "user_activity (all-time)",
        "time_range": "all-time",
        "filters_applied": {
            "excluded_teams": exclude_teams_list,
            "excluded_teams_count": len(exclude_teams_list)
        }
    }


def get_weekly_date_range() -> Tuple[datetime, datetime, str]:
    """
    Calculate the date range for the last complete week (Monday to Sunday) in UTC.
    Uses UTC so the range matches message_events.created_at (stored with datetime.utcnow()).
    
    For testing: If today is Sunday, includes current week (Mon-Sun including today).
    Otherwise: Last complete week (Mon-Sun).
    
    Returns:
        Tuple of (start_date, end_date, date_range_string)
        start_date: Monday at 00:00:00 UTC (naive)
        end_date: Sunday at 23:59:59 UTC (naive)
        date_range_string: Formatted string like "Jan 17, 2026 - Jan 23, 2026"
    """
    today_utc = datetime.utcnow()
    weekday = today_utc.weekday()  # 0=Monday, 6=Sunday
    
    # If today is Sunday (6), include this week (Mon-Sun of current week)
    # Otherwise, use last complete week
    if weekday == 6:  # Sunday - use current week (Mon through today)
        days_since_monday = 6
        last_monday = today_utc - timedelta(days=days_since_monday)
        last_sunday = today_utc  # Today (Sunday)
        logger.info(f"[WEEKLY REPORT] Today is Sunday - using current week (Mon-Sun including today)")
    else:
        # Not Sunday - use last complete week
        days_since_monday = weekday
        last_monday = today_utc - timedelta(days=days_since_monday + 7)
        last_sunday = last_monday + timedelta(days=6)
        logger.info(f"[WEEKLY REPORT] Using last complete week (Mon-Sun)")
    
    # Set times (naive UTC - no tzinfo)
    start_date = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Format date range string for display
    date_range_string = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
    
    logger.info(f"[WEEKLY REPORT] Date range (UTC): {date_range_string} ({start_date} to {end_date})")
    
    return start_date, end_date, date_range_string


async def generate_team_report_data(
    from_date: Optional[datetime],
    to_date: Optional[datetime],
    exclude_teams: Optional[List[str]] = None
) -> Dict:
    """
    Fetch team statistics from the database for the given date range.
    Uses direct MongoDB queries (bypasses HTTP endpoint and authentication).
    
    Args:
        from_date: Start date (datetime), None = all-time data
        to_date: End date (datetime), None = all-time data
        exclude_teams: Optional list of team names to exclude
    
    Returns:
        Dictionary with team statistics (same format as /admin/teams/summary endpoint)
    """
    try:
        from app.mongodb_memory import mongodb_memory
        from app.models.teams import (
            get_team_by_name, get_team_color, get_team_by_member_email, TEAMS_STRUCTURE
        )
        from datetime import timezone
        
        # Ensure MongoDB is connected
        await mongodb_memory.connect()
        
        # Parse exclude_teams
        exclude_teams_list = exclude_teams if exclude_teams else []
        
        # If no dates provided, use all-time data from user_activity (same as UI)
        if not from_date and not to_date:
            logger.info("[WEEKLY REPORT] No dates provided - using ALL-TIME data from user_activity")
            return await _get_all_time_team_data(exclude_teams_list)
        
        # Parse dates - expect naive UTC (from get_weekly_date_range()) to match message_events.created_at (datetime.utcnow())
        start_date = from_date.replace(tzinfo=None) if from_date.tzinfo else from_date
        end_date = to_date.replace(tzinfo=None) if to_date.tzinfo else to_date
        
        # Parse exclude_teams
        exclude_teams_list = exclude_teams if exclude_teams else []
        
        # Query message_events collection for date range (created_at is stored in UTC)
        message_events_collection = mongodb_memory.database["message_events"]
        user_activity_collection = mongodb_memory.database["user_activity"]
        
        # DIAGNOSTIC: Check user_activity for team assignments
        total_user_activity = await user_activity_collection.count_documents({})
        users_with_team = await user_activity_collection.count_documents({"team_name": {"$exists": True, "$ne": "", "$ne": None}})
        logger.info(f"[WEEKLY REPORT] Total user_activity documents: {total_user_activity}, with team_name: {users_with_team}")
        
        # Build date filter (start_date/end_date must be naive UTC for correct match)
        date_filter = {
            "created_at": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        logger.info(f"[WEEKLY REPORT] Querying message_events with created_at between {start_date} and {end_date} (UTC)")
        
        # DIAGNOSTIC: Check total message_events count and matching count
        total_events = await message_events_collection.count_documents({})
        matching_events = await message_events_collection.count_documents(date_filter)
        logger.info(f"[WEEKLY REPORT] Total message_events in collection: {total_events}")
        logger.info(f"[WEEKLY REPORT] Message_events matching date filter ({start_date} to {end_date}): {matching_events}")
        
        # DIAGNOSTIC: Show sample created_at values from message_events to check date format
        if total_events > 0:
            sample_events = await message_events_collection.find({}).sort("created_at", -1).limit(5).to_list(length=5)
            sample_dates = [evt.get("created_at") for evt in sample_events if evt.get("created_at")]
            if sample_dates:
                logger.info(f"[WEEKLY REPORT] Sample created_at values (most recent 5): {sample_dates}")
        
        # If no events in the specified range, check last 30 days for diagnostics
        if matching_events == 0 and total_events > 0:
            last_30_days = datetime.utcnow() - timedelta(days=30)
            recent_filter = {"created_at": {"$gte": last_30_days}}
            recent_count = await message_events_collection.count_documents(recent_filter)
            logger.warning(f"[WEEKLY REPORT] No events in target range, but found {recent_count} events in last 30 days")
            
            # FALLBACK: Use last 7 days if the specified range is empty
            if recent_count > 0:
                logger.warning(f"[WEEKLY REPORT] FALLBACK: Using last 7 days instead of specified range")
                fallback_start = datetime.utcnow() - timedelta(days=7)
                fallback_end = datetime.utcnow()
                date_filter = {
                    "created_at": {
                        "$gte": fallback_start.replace(hour=0, minute=0, second=0, microsecond=0),
                        "$lte": fallback_end
                    }
                }
                start_date = fallback_start.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = fallback_end
                logger.info(f"[WEEKLY REPORT] Fallback range: {start_date} to {end_date}")
        
        # Aggregate messages by user_id
        pipeline = [
            {"$match": date_filter},
            {"$group": {
                "_id": "$user_id",
                "user_email": {"$first": "$user_email"},
                "total_messages": {"$sum": 1}
            }},
            {"$project": {
                "_id": 0,
                "user_id": "$_id",
                "user_email": 1,
                "total_messages": 1
            }}
        ]
        
        user_messages = await message_events_collection.aggregate(pipeline).to_list(length=None)
        logger.info(f"[WEEKLY REPORT] Found {len(user_messages)} users with messages in date range")
        
        # DIAGNOSTIC: Show first few users if any
        if user_messages:
            logger.info(f"[WEEKLY REPORT] Sample users: {user_messages[:3]}")
        
        # FALLBACK: If no users found in message_events for date range, use user_activity (all-time)
        use_all_time_fallback = False
        if len(user_messages) == 0:
            logger.warning(f"[WEEKLY REPORT] No users found in message_events for date range")
            logger.warning(f"[WEEKLY REPORT] FALLBACK: Using all-time data from user_activity instead")
            use_all_time_fallback = True
            
            # Get all user_activity documents (same logic as UI /admin/teams/summary without dates)
            all_users = await user_activity_collection.find({}).to_list(length=None)
            logger.info(f"[WEEKLY REPORT] Found {len(all_users)} users in user_activity (all-time)")
            
            # Convert user_activity format to match message_events format
            user_messages = []
            for user_doc in all_users:
                total_messages = user_doc.get("total_messages", 0)
                if total_messages > 0:  # Only include users with messages
                    user_messages.append({
                        "user_id": user_doc.get("user_id"),
                        "user_email": user_doc.get("user_email", ""),
                        "total_messages": total_messages
                    })
            logger.info(f"[WEEKLY REPORT] Using {len(user_messages)} users from user_activity (all-time) with messages")
        
        # Group by team
        teams_data = {}
        skipped_no_team = 0
        skipped_excluded = 0
        
        for user_msg in user_messages:
            user_id = user_msg.get("user_id")
            user_email = (user_msg.get("user_email") or "").lower()
            total_messages = user_msg.get("total_messages", 0)
            
            # Get team assignment
            team_name = None
            user_doc = None
            
            # Try lookup by user_id first
            if user_id:
                user_doc = await user_activity_collection.find_one(
                    {"user_id": user_id},
                    {"team_name": 1, "user_email": 1, "user_name": 1}
                )
            
            # If not found by user_id, try by user_email
            if not user_doc and user_email:
                user_doc = await user_activity_collection.find_one(
                    {"user_email": user_email},
                    {"team_name": 1, "user_email": 1, "user_name": 1}
                )
            
            if user_doc:
                team_name = user_doc.get("team_name")
                user_name = user_doc.get("user_name", "")
            
            # Fallback to teams.py if not found in user_activity
            if not team_name or team_name.strip() == "":
                if user_email:
                    team_name = get_team_by_member_email(user_email)
                    if team_name == "Unassigned":
                        team_name = None
            
            # Skip users without team assignment or excluded teams
            if not team_name or team_name.strip() == "":
                skipped_no_team += 1
                logger.debug(f"[WEEKLY REPORT] Skipping user {user_email or user_id} - no team assignment")
                continue
            
            if exclude_teams_list and team_name in exclude_teams_list:
                skipped_excluded += 1
                logger.debug(f"[WEEKLY REPORT] Skipping user {user_email or user_id} - team '{team_name}' is excluded")
                continue
            
            # Initialize team if not exists
            if team_name not in teams_data:
                teams_data[team_name] = {
                    "team_name": team_name,
                    "total_messages": 0,
                    "active_members": set(),
                    "member_details": []
                }
            
            # Aggregate team data
            teams_data[team_name]["total_messages"] += total_messages
            teams_data[team_name]["active_members"].add(user_email)
            teams_data[team_name]["member_details"].append({
                "email": user_email,
                "name": user_name if user_doc else "",
                "messages": total_messages
            })
        
        # Convert to list format and get team info from teams.py
        teams_list = []
        for team_name, team_data in teams_data.items():
            team_info = get_team_by_name(team_name)
            if not team_info:
                team_info = {
                    "lead": None,
                    "lead_email": None,
                    "members": [],
                    "color": "#6B7280",
                    "description": team_name
                }
            
            teams_list.append({
                "team_name": team_name,
                "lead": team_info.get("lead"),
                "lead_email": team_info.get("lead_email"),
                "color": get_team_color(team_name) or team_info.get("color", "#6B7280"),
                "description": team_info.get("description", team_name),
                "total_messages": team_data["total_messages"],
                "total_questions": team_data["total_messages"],
                "unique_questions": 0,
                "top_questions": [],
                "active_members_count": len(team_data["active_members"]),
                "member_count": len(team_info.get("members", [])),
                "members": team_data["member_details"]
            })
        
        # Sort by total_messages descending
        teams_list.sort(key=lambda x: x["total_messages"], reverse=True)
        
        logger.info(f"[WEEKLY REPORT] Fetched data for {len(teams_list)} teams")
        logger.info(f"[WEEKLY REPORT] Skipped {skipped_no_team} users (no team), {skipped_excluded} users (excluded teams)")
        if teams_list:
            logger.info(f"[WEEKLY REPORT] Top team: {teams_list[0]['team_name']} with {teams_list[0]['total_messages']} messages")
        
        return {
            "status": "success",
            "total_teams": len(TEAMS_STRUCTURE),
            "teams": teams_list,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": "user_activity (all-time)" if use_all_time_fallback else "message_events",
            "time_range": f"{from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}" if not use_all_time_fallback else "all-time",
            "fallback_used": use_all_time_fallback,
            "filters_applied": {
                "from_date": from_date.strftime("%Y-%m-%d"),
                "to_date": to_date.strftime("%Y-%m-%d"),
                "excluded_teams": exclude_teams_list,
                "excluded_teams_count": len(exclude_teams_list)
            }
        }
        
    except Exception as e:
        logger.error(f"[WEEKLY REPORT] Error fetching team data: {e}", exc_info=True)
        # Fallback: return empty structure
        return {
            "status": "error",
            "teams": [],
            "total_teams": 0,
            "generated_at": datetime.utcnow().isoformat()
        }


def generate_html_email(teams_data: Dict, date_range: str, exclude_note: str = "") -> str:
    """
    Generate HTML email template for team leaderboard report.
    Matches the exact UI from the teams-dashboard page.
    
    Args:
        teams_data: Team statistics dictionary from endpoint
        date_range: Date range string
        exclude_note: Optional note about exclusions (e.g., "Excluding Neutara Labs")
    
    Returns:
        HTML string for email body
    """
    teams = teams_data.get("teams", [])
    total_teams = teams_data.get("total_teams", 0)
    generated_at = teams_data.get("generated_at", datetime.utcnow().isoformat())
    
    # Format generated_at timestamp
    try:
        gen_dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
        gen_str = gen_dt.strftime("%b %d, %Y")
    except:
        gen_str = generated_at
    
    # Get top 5 teams
    top_5_teams = teams[:5]
    
    # Calculate total messages
    total_messages = sum(team.get("total_messages", 0) for team in teams)
    
    # Softer gradient colors for top 5 teams
    # Each card has a gradient from lighter to darker shade for a pleasant effect
    card_gradients = [
        {'from': '#6BA3FF', 'to': '#3B7FFF'},  # 1st - Soft Blue Gradient
        {'from': '#C77AFF', 'to': '#9D4DFF'},  # 2nd - Soft Purple Gradient
        {'from': '#5BC8FF', 'to': '#2BA5FF'},  # 3rd - Soft Cyan-Blue Gradient
        {'from': '#4DD9A3', 'to': '#20CC83'},  # 4th - Soft Green Gradient (using requested color)
        {'from': '#FF9A6B', 'to': '#FF7A4D'},  # 5th - Soft Orange Gradient
    ]
    # Fallback solid colors (for email clients that don't support gradients)
    card_fallback_colors = [
        '#3B7FFF',  # 1st - Medium Blue
        '#9D4DFF',  # 2nd - Medium Purple
        '#2BA5FF',  # 3rd - Medium Cyan-Blue
        '#20CC83',  # 4th - Mint Green (requested)
        '#FF7A4D',  # 5th - Medium Orange
    ]
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            line-height: 1.6;
            color: #323130;
            max-width: 1000px;
            margin: 0 auto;
            padding: 32px;
            background-color: #faf9f8;
        }}
        .container {{
            background-color: white;
            padding: 32px;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
        }}
        h1 {{
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 6px;
            color: #323130;
            border-bottom: 1px solid #e1e5e9;
            padding-bottom: 16px;
        }}
        .info-line {{
            color: #6b7280;
            font-size: 13px;
            margin-bottom: 12px;
        }}
        .info-line strong {{
            color: #111827;
        }}
        .exclusion-note {{
            background-color: #f0f9ff;
            color: #0369a1;
            padding: 12px 14px;
            border-radius: 10px;
            margin-bottom: 16px;
            border: 1px solid #bae6fd;
            font-size: 14px;
        }}
        .top-teams-section {{
            margin-bottom: 32px;
        }}
        .top-teams-section h2 {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 16px;
            color: #111827;
        }}
        .top-teams-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 0;
        }}
        .team-card-cell {{
            width: 20%;
            padding: 0 8px;
            vertical-align: top;
        }}
        .team-card .rank {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .team-card .team-name {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .team-card .description {{
            font-size: 12px;
            opacity: 0.9;
            margin-bottom: 12px;
        }}
        .team-card .messages {{
            font-size: 14px;
            margin-bottom: 4px;
        }}
        .team-card .members {{
            font-size: 14px;
        }}
        .team-card strong {{
            font-weight: 700;
        }}
        .full-leaderboard-section {{
            margin-top: 32px;
            overflow-x: auto;  /* Horizontal scroll container */
            -webkit-overflow-scrolling: touch;  /* Smooth scrolling for iOS */
        }}
        .full-leaderboard-section h2 {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 16px;
            color: #111827;
        }}
        .full-leaderboard-section table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            overflow: hidden;
            display: table;
            table-layout: fixed;  /* Fixed column widths */
            min-width: 960px;  /* Minimum width based on column widths (70+220+200+130+170+170=960px) */
        }}
        @media only screen and (max-width: 600px) {{
            table {{
                display: block !important;
                width: 100% !important;
            }}
            thead {{
                display: none !important;
            }}
            tbody {{
                display: block !important;
                width: 100% !important;
            }}
            tbody tr {{
                display: block !important;
                width: 100% !important;
                margin-bottom: 12px !important;
                border: 1px solid #e5e7eb !important;
                border-radius: 8px !important;
                background: white !important;
            }}
            tbody td {{
                display: block !important;
                width: 100% !important;
                text-align: left !important;
                padding: 12px !important;
                border: none !important;
                border-bottom: 1px solid #f0f0f0 !important;
            }}
            tbody td:last-child {{
                border-bottom: none !important;
            }}
            tbody td:before {{
                content: attr(data-label) ": ";
                font-weight: 600;
                color: #374151;
                display: inline-block;
                min-width: 120px;
            }}
        }}
        thead {{
            background: #f9fafb;
            border-bottom: 2px solid #e5e7eb;
        }}
        th {{
            padding: 14px 16px;  /* Same padding as td for alignment */
            text-align: left;
            font-weight: 600;
            color: #374151;
            font-size: 14px;  /* Increased header font size */
            white-space: nowrap;  /* Prevent header wrapping */
            overflow: hidden;
            text-overflow: ellipsis;
            letter-spacing: 0.3px;  /* Slight letter spacing for clarity */
        }}
        th.text-right {{
            text-align: right;  /* Right align numeric headers */
        }}
        /* Fixed column widths in pixels to prevent overlapping - adjusted for Total Members visibility */
        th:nth-child(1) {{ width: 70px; min-width: 70px; max-width: 70px; }}  /* Rank: 70px */
        th:nth-child(2) {{ width: 200px; min-width: 200px; max-width: 200px; }}  /* Team Name: 200px (reduced) */
        th:nth-child(3) {{ width: 180px; min-width: 180px; max-width: 180px; }}  /* Lead: 180px (reduced) */
        th:nth-child(4) {{ width: 120px; min-width: 120px; max-width: 120px; }}  /* Messages: 120px (reduced) */
        th:nth-child(5) {{ width: 160px; min-width: 160px; max-width: 160px; }}  /* Active Members: 160px (reduced) */
        th:nth-child(6) {{ width: 200px; min-width: 200px; max-width: 200px; }}  /* Total Members: 200px (increased for visibility) */
        tbody tr {{
            border-top: 1px solid #e5e7eb;
        }}
        tbody tr:nth-child(even) {{
            background: #f9fafb;
        }}
        tbody tr:nth-child(odd) {{
            background: white;
        }}
        td {{
            padding: 14px 16px;  /* Same padding as th for perfect alignment */
            color: #111827;
            font-size: 14px;
        }}
        /* Fixed widths matching th columns - adjusted for Total Members visibility */
        td:nth-child(1) {{ width: 70px; min-width: 70px; max-width: 70px; }}  /* Rank: 70px */
        td:nth-child(2) {{ width: 200px; min-width: 200px; max-width: 200px; }}  /* Team Name: 200px (reduced) */
        td:nth-child(3) {{ width: 180px; min-width: 180px; max-width: 180px; }}  /* Lead: 180px (reduced) */
        td:nth-child(4) {{ width: 120px; min-width: 120px; max-width: 120px; text-align: right; }}  /* Messages: 120px, right-aligned (reduced) */
        td:nth-child(5) {{ width: 160px; min-width: 160px; max-width: 160px; text-align: right; }}  /* Active Members: 160px, right-aligned (reduced) */
        td:nth-child(6) {{ width: 200px; min-width: 200px; max-width: 200px; text-align: right; }}  /* Total Members: 200px, right-aligned (increased for visibility) */
        /* Allow wrapping for text columns, prevent for numeric */
        td.rank, td.messages, td.members, td.total-members {{
            white-space: nowrap;  /* Prevent wrapping for numeric columns */
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        td.team-name, td.lead {{
            word-wrap: break-word;  /* Allow wrapping for text columns */
            overflow-wrap: break-word;
        }}
        td.rank {{
            font-weight: 700;
            color: #111827;
            text-align: left;  /* Match PDF alignment */
        }}
        td.team-name {{
            font-weight: 600;
            color: #111827;
            text-align: left;
        }}
        td.messages, td.members, td.total-members {{
            text-align: right;  /* Right align numeric columns */
        }}
        td.lead {{
            color: #6b7280;
            font-size: 13px;
            text-align: left;
        }}
        td.text-right {{
            text-align: right;  /* Right align numeric columns */
        }}
        td.messages {{
            font-weight: 600;
            text-align: right;  /* Right align numeric data */
        }}
        td.members {{
            text-align: right;  /* Right align numeric data */
        }}
        td.total-members {{
            color: #6b7280;
            font-size: 13px;
            text-align: right;  /* Right align numeric data */
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            color: #6b7280;
            font-size: 13px;
        }}
        .footer strong {{
            color: #111827;
        }}
        /* Responsive styles for mobile devices */
        @media only screen and (max-width: 600px) {{
            body {{
                padding: 16px !important;
                max-width: 100% !important;
            }}
            .container {{
                padding: 20px !important;
                width: 100% !important;
                max-width: 100% !important;
            }}
            h1 {{
                font-size: 24px !important;
            }}
            .top-teams-section h2 {{
                font-size: 18px !important;
            }}
            .full-leaderboard-section h2 {{
                font-size: 18px !important;
            }}
            /* Make cards stack vertically on mobile */
            .top-teams-table {{
                width: 100% !important;
            }}
            .top-teams-table tr {{
                display: block !important;
                width: 100% !important;
            }}
            .team-card-cell {{
                display: block !important;
                width: 100% !important;
                max-width: 100% !important;
                padding: 0 0 12px 0 !important;
                margin-bottom: 12px !important;
                box-sizing: border-box !important;
            }}
            .team-card-cell table {{
                width: 100% !important;
                max-width: 100% !important;
            }}
            /* Make table scrollable on mobile with fixed widths */
            .full-leaderboard-section table {{
                display: table !important;  /* Keep table layout for scrolling */
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch !important;
                table-layout: fixed !important;
                min-width: 930px !important;  /* Minimum width: 70+200+180+120+160+200=930px */
            }}
            .full-leaderboard-section {{
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch !important;
            }}
            .full-leaderboard-section thead, .full-leaderboard-section tbody, .full-leaderboard-section th, .full-leaderboard-section td, .full-leaderboard-section tr {{
                display: table-row !important;  /* Maintain table structure for scrolling */
                width: auto !important;
            }}
            .full-leaderboard-section th {{
                white-space: nowrap !important;  /* Ensure headers don't wrap */
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Team Leaderboard</h1>
        
        <div class="info-line">
            Last updated: <strong>{gen_str}</strong>
            {' • '}
            Total teams: <strong>{total_teams}</strong>
            {' • '}
            <span style="color: #059669; font-weight: 500;">Date Range: {date_range}</span>
        </div>
"""
    
    if exclude_note:
        html += f"""
        <div class="exclusion-note">
            <strong>Note:</strong> {exclude_note}
        </div>
"""
    
    html += """
        <div class="top-teams-section">
            <h2>Top 5 Teams</h2>
            <table class="top-teams-table" width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; border-collapse: collapse; margin: 0;">
                <tr>
"""
    
    # Add top 5 team cards with gradient colors (with fallback for email compatibility)
    for idx, team in enumerate(top_5_teams, 1):
        if idx <= 5:
            gradient = card_gradients[idx - 1]
            fallback_color = card_fallback_colors[idx - 1]
            # Create gradient CSS with fallback
            gradient_css = f"background: {fallback_color}; background: linear-gradient(135deg, {gradient['from']} 0%, {gradient['to']} 100%); -webkit-background: linear-gradient(135deg, {gradient['from']} 0%, {gradient['to']} 100%);"
        else:
            fallback_color = '#f9fafb'
            gradient_css = f"background-color: {fallback_color};"
        
        text_color = '#ffffff'  # White text for all cards
        team_name = team.get("team_name", "Unknown")
        description = team.get("description", team_name)
        messages = team.get("total_messages", 0)
        active_members = team.get("active_members_count", 0)
        
        html += f"""
                    <td class="team-card-cell" width="20%" style="width: 20%; padding: 0 8px; vertical-align: top;">
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; border-collapse: collapse; {gradient_css} border-radius: 12px; height: 200px;">
                            <tr>
                                <td style="padding: 20px; text-align: center; {gradient_css} border-radius: 12px; height: 200px; vertical-align: middle; width: 100%;">
                                    <div style="font-size: 32px; font-weight: 700; margin-bottom: 8px; color: {text_color}; line-height: 1.2;">#{idx}</div>
                                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 4px; color: {text_color}; line-height: 1.3;">{team_name}</div>
                                    <div style="font-size: 12px; margin-bottom: 12px; color: {text_color}; opacity: 0.95; line-height: 1.4;">{description}</div>
                                    <div style="font-size: 14px; margin-bottom: 4px; color: {text_color}; line-height: 1.5;"><strong style="font-weight: 700;">{messages:,}</strong> messages</div>
                                    <div style="font-size: 14px; color: {text_color}; line-height: 1.5;"><strong style="font-weight: 700;">{active_members}</strong> active members</div>
                                </td>
                            </tr>
                        </table>
                    </td>
"""
    
    html += """
                </tr>
            </table>
        </div>
        
        <div class="full-leaderboard-section">
            <h2>Full Leaderboard</h2>
            <table>
                <thead>
                    <tr>
                        <th style="text-align: left; width: 70px; min-width: 70px; max-width: 70px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Rank</th>
                        <th style="text-align: left; width: 200px; min-width: 200px; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Team Name</th>
                        <th style="text-align: left; width: 180px; min-width: 180px; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Lead</th>
                        <th class="text-right" style="text-align: right; width: 120px; min-width: 120px; max-width: 120px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Messages</th>
                        <th class="text-right" style="text-align: right; width: 160px; min-width: 160px; max-width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Active Members</th>
                        <th class="text-right" style="text-align: right; width: 200px; min-width: 200px; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Total Members</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    # Add all teams to table
    for idx, team in enumerate(teams, 1):
        team_name = team.get("team_name", "Unknown")
        lead = team.get("lead", "—")
        messages = team.get("total_messages", 0)
        active_members = team.get("active_members_count", 0)
        total_members = team.get("member_count", 0)
        
        html += f"""
                    <tr>
                        <td class="rank" data-label="Rank">{idx}</td>
                        <td class="team-name" data-label="Team Name">{team_name}</td>
                        <td class="lead" data-label="Lead">{lead}</td>
                        <td class="messages" data-label="Messages">{messages:,}</td>
                        <td class="members" data-label="Active Members">{active_members:,}</td>
                        <td class="total-members" data-label="Total Members">{total_members:,}</td>
                    </tr>
"""
    
    html += f"""
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>Total Messages: <strong>{total_messages:,}</strong></p>
            <p>This is an automated weekly report generated by the CloudFuze Team Leaderboard system.</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html


def create_pie_chart(top_5_teams: List[Dict]) -> io.BytesIO:
    """Create a pie chart for top 5 teams matching dashboard colors."""
    if not top_5_teams:
        return None
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    team_names = [team.get("team_name", "Unknown")[:20] for team in top_5_teams]
    messages = [team.get("total_messages", 0) for team in top_5_teams]
    
    # Use dashboard colors
    colors_list = COLORS[:len(top_5_teams)]
    
    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        messages,
        labels=team_names,
        autopct='%1.1f%%',
        colors=colors_list,
        startangle=90
    )
    
    # Improve text appearance
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(10)
    
    ax.set_title('Message Distribution (Top 5)', fontsize=14, fontweight='bold', pad=20)
    
    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf


def create_bar_chart(teams: List[Dict], max_teams: int = 10) -> io.BytesIO:
    """Create a bar chart for top teams matching dashboard colors."""
    if not teams:
        return None
    
    # Take top N teams
    top_teams = teams[:max_teams]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    team_names = [team.get("team_name", "Unknown")[:15] for team in top_teams]
    messages = [team.get("total_messages", 0) for team in top_teams]
    
    # Use dashboard color (#3b82f6) for all bars
    bar_color = '#3b82f6'
    
    # Create bar chart
    bars = ax.bar(range(len(team_names)), messages, color=bar_color)
    
    # Add value labels on bars
    for i, (bar, msg) in enumerate(zip(bars, messages)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{msg:,}',
                ha='center', va='bottom', fontweight='bold')
    
    ax.set_xlabel('Teams', fontsize=12, fontweight='bold')
    ax.set_ylabel('Messages', fontsize=12, fontweight='bold')
    ax.set_title('Top Teams by Messages', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(range(len(team_names)))
    ax.set_xticklabels(team_names, rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    
    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf


def generate_pdf_report(
    teams_data: Dict,
    date_range: str,
    output_path: str,
    exclude_note: str = ""
) -> str:
    """
    Generate PDF report with team leaderboard data and charts.
    
    Args:
        teams_data: Team statistics dictionary from endpoint
        date_range: Date range string
        output_path: Path where PDF should be saved
        exclude_note: Optional note about exclusions
    
    Returns:
        Path to generated PDF file
    """
    try:
        teams = teams_data.get("teams", [])
        total_teams = teams_data.get("total_teams", 0)
        generated_at = teams_data.get("generated_at", datetime.utcnow().isoformat())
        
        # Format generated_at timestamp
        try:
            gen_dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
            gen_str = gen_dt.strftime("%b %d, %Y")
        except:
            gen_str = generated_at
        
        # Create PDF document with better margins
        doc = SimpleDocTemplate(output_path, pagesize=letter, 
                                rightMargin=0.5*inch, leftMargin=0.5*inch,
                                topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles matching dashboard (reduced font sizes)
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor('#323130'),
            spaceAfter=6,
            fontName='Helvetica-Bold',
            alignment=0  # Left
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#111827'),
            spaceAfter=12,
            fontName='Helvetica-Bold',
            alignment=0  # Left
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=8,
            fontName='Helvetica'
        )
        
        # Title
        story.append(Paragraph("Team Leaderboard", title_style))
        story.append(Spacer(1, 0.08*inch))
        
        # Info line
        info_text = f'<font color="#6b7280" size="10">Last updated: <b><font color="#111827">{gen_str}</font></b> • Total teams: <b><font color="#111827">{total_teams}</font></b> • <font color="#059669"><b>Date Range: {date_range}</b></font></font>'
        story.append(Paragraph(info_text, styles['Normal']))
        story.append(Spacer(1, 0.15*inch))
        
        if exclude_note:
            note_text = f'<font color="#0369a1" size="11"><b>Note:</b> {exclude_note}</font>'
            story.append(Paragraph(note_text, styles['Normal']))
            story.append(Spacer(1, 0.15*inch))
        
        # Top 5 Teams Section - Table Format
        top_5 = teams[:5]
        if top_5:
            story.append(Paragraph("Top 5 Teams", heading_style))
            story.append(Spacer(1, 0.15*inch))
            
            # Create table data with headers
            top5_table_data = [['Rank', 'Team Name', 'Messages', 'Active Members']]
            for idx, team in enumerate(top_5, 1):
                team_name = team.get("team_name", "Unknown")
                messages = team.get("total_messages", 0)
                active_members = team.get("active_members_count", 0)
                
                # Add row data: Rank (with #), Team Name, Messages, Active Members
                top5_table_data.append([
                    f"#{idx}",
                    team_name,
                    f"{messages:,}",
                    f"{active_members:,}"
                ])
            
            # Create table with fixed column widths (converted from pixels to inches)
            # Rank: 80px ≈ 0.8", Team Name: 280px ≈ 2.8", Messages: 140px ≈ 1.4", Active Members: 170px ≈ 1.7"
            # Total: 0.8 + 2.8 + 1.4 + 1.7 = 6.7 inches (fits within page width)
            # Increased widths to prevent header overlap
            top5_table = Table(top5_table_data, colWidths=[0.8*inch, 2.8*inch, 1.4*inch, 1.7*inch])
            top5_table.setStyle(TableStyle([
                # Header row styling - fixed widths, no wrapping, larger font
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9fafb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 13),  # Header font size
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # More spacing
                ('TOPPADDING', (0, 0), (-1, 0), 12),  # More spacing
                ('LEFTPADDING', (0, 0), (-1, 0), 12),  # Increased padding for spacing
                ('RIGHTPADDING', (0, 0), (-1, 0), 12),  # Increased padding for spacing
                # Alignment - Header row (must match data alignment)
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),    # Rank header left
                ('ALIGN', (1, 0), (1, 0), 'LEFT'),    # Team name header left
                ('ALIGN', (2, 0), (2, 0), 'RIGHT'),   # Messages header right (numeric)
                ('ALIGN', (3, 0), (3, 0), 'RIGHT'),   # Active members header right (numeric)
                # Alignment - Data rows (must match header alignment)
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Rank left
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Team name left
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),  # Messages right (numeric)
                ('ALIGN', (3, 1), (3, -1), 'RIGHT'),   # Active members right (numeric)
                # Data row styling - same padding as headers for alignment
                ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
                ('TOPPADDING', (0, 1), (-1, -1), 10),
                ('LEFTPADDING', (0, 1), (-1, -1), 12),  # Same padding as headers
                ('RIGHTPADDING', (0, 1), (-1, -1), 12),  # Same padding as headers
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),  # Light gray borders
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),  # Alternating row colors
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Rank bold
                ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),  # Team name bold
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(top5_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Charts - store temp file paths for cleanup
        temp_chart_files = []
        chart_width = 6.0*inch  # Wider for full-width charts
        chart_height = 4.0*inch  # Taller for better visibility
        
        # Pie Chart (under Top 5 Teams table)
        if top_5:
            pie_chart = create_pie_chart(top_5)
            
            # Save pie chart to temporary file
            pie_img_path = None
            if pie_chart:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    pie_chart.seek(0)
                    tmp_file.write(pie_chart.read())
                    pie_img_path = tmp_file.name
                    temp_chart_files.append(pie_img_path)
            
            if pie_img_path:
                pie_title = Paragraph("Message Distribution (Top 5)", normal_style)
                story.append(pie_title)
                story.append(Spacer(1, 0.1*inch))
                pie_img = Image(pie_img_path, width=chart_width, height=chart_height)
                story.append(pie_img)
                story.append(Spacer(1, 0.3*inch))
            else:
                story.append(Paragraph("Chart not available", normal_style))
                story.append(Spacer(1, 0.3*inch))
        
        # Bar Chart (next page)
        story.append(PageBreak())
        if top_5:
            bar_chart = create_bar_chart(teams, max_teams=10)
            
            # Save bar chart to temporary file
            bar_img_path = None
            if bar_chart:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    bar_chart.seek(0)
                    tmp_file.write(bar_chart.read())
                    bar_img_path = tmp_file.name
                    temp_chart_files.append(bar_img_path)
            
            if bar_img_path:
                bar_title = Paragraph("Top Teams by Messages", normal_style)
                story.append(bar_title)
                story.append(Spacer(1, 0.1*inch))
                bar_img = Image(bar_img_path, width=chart_width, height=chart_height)
                story.append(bar_img)
                story.append(Spacer(1, 0.3*inch))
            else:
                story.append(Paragraph("Chart not available", normal_style))
                story.append(Spacer(1, 0.3*inch))
        
        # Full Leaderboard Table (under bar chart)
        story.append(Paragraph("Full Leaderboard", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        table_data = [['Rank', 'Team Name', 'Lead', 'Messages', 'Active Members', 'Total Members']]
        for idx, team in enumerate(teams, 1):
            table_data.append([
                str(idx),
                team.get("team_name", "Unknown"),
                team.get("lead", "—"),
                f"{team.get('total_messages', 0):,}",
                f"{team.get('active_members_count', 0):,}",
                f"{team.get('member_count', 0):,}"
            ])
        
        # Calculate column widths - adjusted to ensure Total Members column is clearly visible
        # Redistributed widths: Rank: 0.5", Team Name: 1.6", Lead: 1.4", Messages: 1.0", Active: 1.3", Total: 1.7"
        # Total: 0.5 + 1.6 + 1.4 + 1.0 + 1.3 + 1.7 = 7.5 inches (perfect fit)
        # Increased Total Members width to 1.7" for better visibility
        table = Table(table_data, colWidths=[0.5*inch, 1.6*inch, 1.4*inch, 1.0*inch, 1.3*inch, 1.7*inch])
        table.setStyle(TableStyle([
            # Header row styling - fixed widths, no wrapping, larger font, increased padding
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9fafb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 13),  # Increased header font size
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # More spacing
            ('TOPPADDING', (0, 0), (-1, 0), 12),  # More spacing
            ('LEFTPADDING', (0, 0), (-1, 0), 12),  # Increased padding for spacing (matches data)
            ('RIGHTPADDING', (0, 0), (-1, 0), 12),  # Increased padding for spacing (matches data)
            # Alignment - Header row (must match data alignment)
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),    # Rank header left
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),    # Team name header left
            ('ALIGN', (2, 0), (2, 0), 'LEFT'),    # Lead header left
            ('ALIGN', (3, 0), (3, 0), 'RIGHT'),   # Messages header right (numeric)
            ('ALIGN', (4, 0), (4, 0), 'RIGHT'),   # Active members header right (numeric)
            ('ALIGN', (5, 0), (5, 0), 'RIGHT'),   # Total members header right (numeric)
            # Alignment - Data rows (must match header alignment)
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Rank left
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Team name left
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),    # Lead left
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),  # Messages right (numeric)
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),   # Active members right (numeric)
            ('ALIGN', (5, 1), (5, -1), 'RIGHT'),  # Total members right (numeric)
            # Data row styling - same padding as headers for perfect alignment
            ('BOTTOMPADDING', (0, 1), (-1, -1), 10),  # More spacing
            ('TOPPADDING', (0, 1), (-1, -1), 10),  # More spacing
            ('LEFTPADDING', (0, 1), (-1, -1), 12),  # Same padding as headers
            ('RIGHTPADDING', (0, 1), (-1, -1), 12),  # Same padding as headers
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Rank bold
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),  # Team name bold
            ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#6b7280')),  # Lead gray
            ('FONTSIZE', (2, 1), (2, -1), 9),  # Lead smaller
            ('TEXTCOLOR', (5, 1), (5, -1), colors.HexColor('#6b7280')),  # Total members gray
            ('FONTSIZE', (5, 1), (5, -1), 9),  # Total members smaller
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(table)
        
        # Summary Section - Move to next page
        story.append(PageBreak())
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph("Summary", heading_style))
        story.append(Spacer(1, 0.15*inch))
        
        # Calculate summary statistics
        total_messages = sum(team.get("total_messages", 0) for team in teams)
        total_active_members = sum(team.get("active_members_count", 0) for team in teams)
        top_team = teams[0] if teams else None
        avg_messages_per_team = total_messages / len(teams) if teams else 0
        
        # Generate summary text (4-5 lines) with line spacing
        summary_lines = []
        if top_team:
            summary_lines.append(f"This weekly report covers team activity from {date_range}, analyzing performance across {len(teams)} teams.")
            summary_lines.append(f"The top-performing team was {top_team.get('team_name', 'Unknown')} with {top_team.get('total_messages', 0):,} messages and {top_team.get('active_members_count', 0)} active members.")
            summary_lines.append(f"Overall, teams generated a total of {total_messages:,} messages with {total_active_members} active members participating during this period.")
            summary_lines.append(f"The average team activity was {avg_messages_per_team:.1f} messages per team, indicating {'strong' if avg_messages_per_team > 10 else 'moderate' if avg_messages_per_team > 5 else 'developing'} engagement levels.")
            if exclude_note:
                summary_lines.append(f"Note: {exclude_note}.")
        else:
            summary_lines.append(f"This weekly report covers team activity from {date_range}.")
            summary_lines.append(f"No team data was available for the specified period.")
        
        # Create summary paragraphs with line spacing between each line
        # Use double <br/> tags for more spacing between lines
        summary_text = "<br/><br/>".join(summary_lines)
        
        # Create a custom style with increased leading (line spacing)
        summary_style = ParagraphStyle(
            'SummaryStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6b7280'),
            leading=16,  # Line spacing (font size * 1.6 for comfortable reading)
            spaceAfter=6,  # Space after paragraph
        )
        
        summary_para = Paragraph(summary_text, summary_style)
        story.append(summary_para)
        
        # Footer (reduced font size)
        story.append(Spacer(1, 0.3*inch))
        footer_text = f'<font color="#6b7280" size="10">Total Messages: <b><font color="#111827">{total_messages:,}</font></b></font><br/><font color="#6b7280" size="10">This is an automated weekly report generated by the CloudFuze Team Leaderboard system.</font>'
        story.append(Paragraph(footer_text, styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        # Clean up temporary chart files
        for temp_file in temp_chart_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"[WEEKLY REPORT] Failed to delete temp chart file {temp_file}: {e}")
        
        logger.info(f"[WEEKLY REPORT] PDF generated: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[WEEKLY REPORT] Error generating PDF: {e}", exc_info=True)
        raise
