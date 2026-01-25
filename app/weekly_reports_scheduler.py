# -*- coding: utf-8 -*-
"""
Weekly Reports Scheduler

Scheduled task that generates and sends weekly team leaderboard reports.
"""

import os
import logging
import tempfile
from datetime import datetime
from app.weekly_reports import (
    get_weekly_date_range,
    generate_team_report_data,
    generate_html_email,
    generate_pdf_report
)
from app.email_sender import send_weekly_report_emails

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
        
        # Get date range for last week (Monday to Sunday)
        start_date, end_date, date_range_str = get_weekly_date_range()
        
        # Create temporary directory for PDF files
        temp_dir = tempfile.mkdtemp(prefix="weekly_reports_")
        logger.info(f"[WEEKLY REPORT] Using temp directory: {temp_dir}")
        
        try:
            # Generate report data with Neutara Labs excluded
            logger.info("[WEEKLY REPORT] Fetching team data (excluding Neutara Labs)...")
            teams_data_with_exclusion = await generate_team_report_data(
                from_date=start_date,
                to_date=end_date,
                exclude_teams=["Neutara Labs"]
            )
            
            # Generate report data without exclusions
            logger.info("[WEEKLY REPORT] Fetching team data (all teams)...")
            teams_data_without_exclusion = await generate_team_report_data(
                from_date=start_date,
                to_date=end_date,
                exclude_teams=None
            )
            
            # Generate HTML emails
            logger.info("[WEEKLY REPORT] Generating HTML email templates...")
            html_with_exclusion = generate_html_email(
                teams_data_with_exclusion,
                date_range_str,
                exclude_note="Excluding Neutara Labs teams"
            )
            
            html_without_exclusion = generate_html_email(
                teams_data_without_exclusion,
                date_range_str,
                exclude_note=""
            )
            
            # Generate PDF reports
            logger.info("[WEEKLY REPORT] Generating PDF reports...")
            pdf_path_with_exclusion = os.path.join(temp_dir, "report_without_neutara.pdf")
            pdf_path_without_exclusion = os.path.join(temp_dir, "report_all_teams.pdf")
            
            generate_pdf_report(
                teams_data_with_exclusion,
                date_range_str,
                pdf_path_with_exclusion,
                exclude_note="Excluding Neutara Labs teams"
            )
            
            generate_pdf_report(
                teams_data_without_exclusion,
                date_range_str,
                pdf_path_without_exclusion,
                exclude_note=""
            )
            
            # Send emails
            logger.info("[WEEKLY REPORT] Sending emails...")
            success = send_weekly_report_emails(
                report_data_with_exclusion=teams_data_with_exclusion,
                report_data_without_exclusion=teams_data_without_exclusion,
                date_range=date_range_str,
                html_body_with_exclusion=html_with_exclusion,
                html_body_without_exclusion=html_without_exclusion,
                pdf_path_with_exclusion=pdf_path_with_exclusion,
                pdf_path_without_exclusion=pdf_path_without_exclusion
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
    """
    import asyncio
    
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run the async function
    loop.run_until_complete(scheduled_weekly_reports())
