# -*- coding: utf-8 -*-
"""
Email Sender Module

Sends emails via Microsoft Graph API with HTML body and PDF attachments.
Uses existing SharePoint authentication for Microsoft Graph API access.
"""

import os
import base64
import logging
import requests
from typing import List, Optional
from app.sharepoint_auth import sharepoint_auth
from app.auth import ADMIN_EMAILS

logger = logging.getLogger(__name__)


def send_email_via_graph_api(
    to_emails: List[str],
    subject: str,
    html_body: str,
    pdf_attachment_path: Optional[str] = None,
    pdf_attachment_name: Optional[str] = None
) -> bool:
    """
    Send email via Microsoft Graph API with HTML body and optional PDF attachment.
    
    Args:
        to_emails: List of recipient email addresses
        subject: Email subject line
        html_body: HTML content for email body
        pdf_attachment_path: Optional path to PDF file to attach
        pdf_attachment_name: Optional name for the PDF attachment (if not provided, uses filename from path)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Get authentication headers
        headers = sharepoint_auth.get_headers()
        
        # Prepare recipients
        recipients = [{"emailAddress": {"address": email}} for email in to_emails]
        
        # Build message body
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body
                },
                "toRecipients": recipients
            }
        }
        
        # Add attachment if provided
        if pdf_attachment_path and os.path.exists(pdf_attachment_path):
            try:
                # Read PDF file and encode as base64
                with open(pdf_attachment_path, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()
                    pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
                
                # Determine attachment name
                attachment_name = pdf_attachment_name or os.path.basename(pdf_attachment_path)
                
                # Add attachment to message
                if "attachments" not in message["message"]:
                    message["message"]["attachments"] = []
                
                message["message"]["attachments"].append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment_name,
                    "contentType": "application/pdf",
                    "contentBytes": pdf_base64
                })
                
                logger.info(f"[EMAIL] Added PDF attachment: {attachment_name} ({len(pdf_content)} bytes)")
            except Exception as e:
                logger.error(f"[EMAIL] Failed to attach PDF: {e}", exc_info=True)
                # Continue without attachment rather than failing completely
        
        # Get sender email from environment or use first admin email
        sender_email = os.getenv("WEEKLY_REPORT_SENDER_EMAIL") or list(ADMIN_EMAILS)[0]
        
        # Send email via Microsoft Graph API
        # Note: For application permissions, we need to send on behalf of a user
        # The sender_email must be a valid user in the tenant
        send_mail_url = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
        
        logger.info(f"[EMAIL] Sending email to {len(to_emails)} recipients via Graph API...")
        logger.info(f"[EMAIL] Subject: {subject}")
        logger.info(f"[EMAIL] Sender: {sender_email}")
        
        response = requests.post(
            send_mail_url,
            headers=headers,
            json=message,
            timeout=60
        )
        
        if response.status_code in [200, 202]:
            logger.info(f"[EMAIL] ✅ Email sent successfully to {len(to_emails)} recipients")
            return True
        else:
            logger.error(f"[EMAIL] ❌ Failed to send email: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"[EMAIL] ❌ Error sending email: {e}", exc_info=True)
        return False


def send_weekly_report_email(
    report_data: dict,
    date_range: str,
    html_body: str,
    pdf_path: Optional[str] = None,
    exclude_note: Optional[str] = None
) -> bool:
    """
    Send a single weekly report email to admin users (used by the scheduler).
    Uses Microsoft Graph API with HTML body and optional PDF attachment.

    Args:
        report_data: Team statistics dict (for logging; not used for content)
        date_range: Date range string for subject line
        html_body: HTML content for email body
        pdf_path: Optional path to PDF attachment
        exclude_note: Optional note about exclusions (e.g. "Excluding Neutara Labs")

    Returns:
        True if email sent successfully, False otherwise
    """
    admin_email_list = list(ADMIN_EMAILS)
    if not admin_email_list:
        logger.error("[EMAIL] No admin emails configured")
        return False

    subject = f"Weekly Team Leaderboard Report - {date_range}"
    if exclude_note:
        subject = f"{subject} ({exclude_note})"
    pdf_name = f"Team_Leaderboard_Report_{date_range.replace(' ', '_')}.pdf" if date_range else "weekly_report.pdf"

    return send_email_via_graph_api(
        to_emails=admin_email_list,
        subject=subject,
        html_body=html_body,
        pdf_attachment_path=pdf_path,
        pdf_attachment_name=pdf_name
    )


def send_weekly_report_emails(
    report_data_with_exclusion: dict,
    report_data_without_exclusion: dict,
    date_range: str,
    html_body_with_exclusion: str,
    html_body_without_exclusion: str,
    pdf_path_with_exclusion: str,
    pdf_path_without_exclusion: str
) -> bool:
    """
    Send weekly report emails to admin users.
    Sends two emails: one with Neutara Labs excluded, one without.
    
    Args:
        report_data_with_exclusion: Team data with Neutara Labs excluded
        report_data_without_exclusion: Team data without exclusions
        date_range: Date range string for the report
        html_body_with_exclusion: HTML email body for excluded version
        html_body_without_exclusion: HTML email body for non-excluded version
        pdf_path_with_exclusion: Path to PDF for excluded version
        pdf_path_without_exclusion: Path to PDF for non-excluded version
    
    Returns:
        True if all emails sent successfully, False otherwise
    """
    admin_email_list = list(ADMIN_EMAILS)
    
    if not admin_email_list:
        logger.error("[EMAIL] No admin emails configured")
        return False
    
    # Generate PDF attachment names
    pdf_name_with_exclusion = f"Team_Leaderboard_Report_{date_range.replace(' ', '_')}_Without_NeutaraLabs.pdf"
    pdf_name_without_exclusion = f"Team_Leaderboard_Report_{date_range.replace(' ', '_')}_All_Teams.pdf"
    
    # Send email with exclusion
    subject_with_exclusion = f"Weekly Team Leaderboard Report - {date_range} (Excluding Neutara Labs)"
    success1 = send_email_via_graph_api(
        to_emails=admin_email_list,
        subject=subject_with_exclusion,
        html_body=html_body_with_exclusion,
        pdf_attachment_path=pdf_path_with_exclusion,
        pdf_attachment_name=pdf_name_with_exclusion
    )
    
    # Send email without exclusion
    subject_without_exclusion = f"Weekly Team Leaderboard Report - {date_range} (All Teams)"
    success2 = send_email_via_graph_api(
        to_emails=admin_email_list,
        subject=subject_without_exclusion,
        html_body=html_body_without_exclusion,
        pdf_attachment_path=pdf_path_without_exclusion,
        pdf_attachment_name=pdf_name_without_exclusion
    )
    
    if success1 and success2:
        logger.info("[EMAIL] ✅ All weekly report emails sent successfully")
        return True
    else:
        logger.warning(f"[EMAIL] ⚠️  Some emails failed to send (exclusion: {success1}, all teams: {success2})")
        return False
