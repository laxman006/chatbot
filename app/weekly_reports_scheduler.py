# -*- coding: utf-8 -*-
"""
Weekly Reports Scheduler

Scheduled task that generates and sends weekly team leaderboard reports.
"""

import os
import logging
import tempfile
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.weekly_reports import (
    get_weekly_date_range,
    generate_html_email,
    generate_pdf_report
)
from app.email_sender import send_weekly_report_email
from app.models.teams import get_team_by_name, get_team_color, get_team_by_member_email, TEAMS_STRUCTURE

logger = logging.getLogger(__name__)


async def scheduled_weekly_reports():
    """
    Background job for scheduled weekly reports.
    Runs every Monday at the configured time to generate and send reports.
    """
    try:
        logger.info("="*70)
        logger.info("[WEEKLY REPORT] 🔄 Starting scheduled weekly report generation...")
        logger.info(f"[WEEKLY REPORT] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*70)
        
        # Get date range for display purposes (Monday to Sunday)
        start_date, end_date, date_range_str = get_weekly_date_range()
        
        # Create temporary directory for PDF files
        temp_dir = tempfile.mkdtemp(prefix="weekly_reports_")
        logger.info(f"[WEEKLY REPORT] Using temp directory: {temp_dir}")
        
        try:
            # Single report: exclude Neutara Labs and Marketing team
            EXCLUDE_TEAMS = ["Neutara Labs", "Marketing"]
            logger.info(f"[WEEKLY REPORT] Fetching DATE-FILTERED team data for {date_range_str}...")
            
            # Create a fresh MongoDB connection for this event loop (avoids motor loop mismatch)
            from config import MONGODB_URL
            mongo_client = AsyncIOMotorClient(MONGODB_URL)
            db = mongo_client["slack2teams"]
            message_events_collection = db["message_events"]
            user_activity_collection = db["user_activity"]
            
            # Query message_events for the date range (same as UI with dates)
            date_filter = {
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            # Debug: Check what we have
            total_events = await message_events_collection.count_documents({})
            matching_events = await message_events_collection.count_documents(date_filter)
            logger.info(f"[WEEKLY REPORT] Total message_events: {total_events}, matching date filter: {matching_events}")
            
            # Aggregate by user_id for the date range
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
            
            # Group by team (same logic as UI endpoint for date-filtered data)
            teams_data_dict = {}
            for user_msg in user_messages:
                user_id = user_msg.get("user_id")
                user_email = (user_msg.get("user_email") or "").lower()
                total_messages = user_msg.get("total_messages", 0)
                
                # Get team_name from user_activity
                team_name = None
                user_name = ""
                
                # Try lookup by user_id first
                if user_id:
                    user_doc = await user_activity_collection.find_one(
                        {"user_id": user_id},
                        {"team_name": 1, "user_email": 1, "user_name": 1}
                    )
                    if user_doc:
                        team_name = user_doc.get("team_name")
                        user_name = user_doc.get("user_name", "")
                
                # Try by email if not found
                if not team_name and user_email:
                    user_doc = await user_activity_collection.find_one(
                        {"user_email": user_email},
                        {"team_name": 1, "user_email": 1, "user_name": 1}
                    )
                    if user_doc:
                        team_name = user_doc.get("team_name")
                        user_name = user_doc.get("user_name", "")
                
                # Fallback to teams.py if needed
                if not team_name or team_name.strip() == "":
                    if user_email:
                        team_name = get_team_by_member_email(user_email)
                        if team_name == "Unassigned":
                            continue
                    else:
                        continue
                
                # Skip excluded teams
                if team_name in EXCLUDE_TEAMS:
                    continue
                
                if team_name not in teams_data_dict:
                    teams_data_dict[team_name] = {
                        "team_name": team_name,
                        "total_messages": 0,
                        "active_members": set(),
                        "member_details": []
                    }
                
                teams_data_dict[team_name]["total_messages"] += total_messages
                teams_data_dict[team_name]["active_members"].add(user_email)
                teams_data_dict[team_name]["member_details"].append({
                    "email": user_email,
                    "name": user_name,
                    "messages": total_messages
                })
            
            # Convert to list and add team info
            teams_list = []
            for team_name, team_data in teams_data_dict.items():
                team_info = get_team_by_name(team_name) or {
                    "lead": None, "lead_email": None, "members": [], "color": "#6B7280", "description": team_name
                }
                teams_list.append({
                    "team_name": team_name,
                    "lead": team_info.get("lead"),
                    "lead_email": team_info.get("lead_email"),
                    "color": get_team_color(team_name) or "#6B7280",
                    "description": team_info.get("description", team_name),
                    "total_messages": team_data["total_messages"],
                    "active_members_count": len(team_data["active_members"]),
                    "member_count": len(team_info.get("members", [])),
                    "members": team_data["member_details"]
                })
            
            teams_list.sort(key=lambda x: x["total_messages"], reverse=True)
            
            teams_data = {
                "teams": teams_list,
                "total_teams": len(TEAMS_STRUCTURE),
                "data_source": f"message_events ({date_range_str})"
            }
            
            # Close the MongoDB connection
            mongo_client.close()
            
            logger.info(f"[WEEKLY REPORT] Fetched {len(teams_list)} teams for {date_range_str} (excluding {EXCLUDE_TEAMS})")
            if teams_list:
                logger.info(f"[WEEKLY REPORT] Top team: {teams_list[0]['team_name']} with {teams_list[0]['total_messages']} messages")
            else:
                logger.warning(f"[WEEKLY REPORT] No teams with messages in date range {date_range_str}")
            
            # Build exclude note
            exclude_note = f"Excluding Neutara Labs and Marketing"
            
            # Generate HTML email
            logger.info("[WEEKLY REPORT] Generating HTML email template...")
            html_body = generate_html_email(
                teams_data,
                date_range_str,
                exclude_note=exclude_note
            )
            
            # Generate PDF report
            logger.info("[WEEKLY REPORT] Generating PDF report...")
            pdf_path = os.path.join(temp_dir, "weekly_report.pdf")
            generate_pdf_report(
                teams_data,
                date_range_str,
                pdf_path,
                exclude_note=exclude_note
            )
            
            # Send single email
            logger.info("[WEEKLY REPORT] Sending email...")
            success = send_weekly_report_email(
                report_data=teams_data,
                date_range=date_range_str,
                html_body=html_body,
                pdf_path=pdf_path,
                exclude_note=exclude_note
            )
            
            if success:
                logger.info("="*70)
                logger.info("[WEEKLY REPORT] ✅ Weekly report generation completed successfully")
                logger.info("="*70)
            else:
                logger.warning("="*70)
                logger.warning("[WEEKLY REPORT] ⚠️  Weekly report generation completed with warnings")
                logger.warning("="*70)
        
        finally:
            # Clean up temporary files
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"[WEEKLY REPORT] Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"[WEEKLY REPORT] Failed to clean up temp directory: {e}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[WEEKLY REPORT] ❌ Weekly report generation failed: {error_msg}", exc_info=True)


def scheduled_weekly_reports_sync():
    """
    Synchronous wrapper for the async scheduled_weekly_reports function.
    This is needed because APScheduler runs functions synchronously.
    Uses asyncio.run() to create a fresh event loop each time (fixes motor/MongoDB loop mismatch).
    """
    import asyncio
    
    # Use asyncio.run() to create a fresh loop each time
    # This ensures MongoDB (motor) operations work correctly in the scheduler context
    asyncio.run(scheduled_weekly_reports())
