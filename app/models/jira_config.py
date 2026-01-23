# -*- coding: utf-8 -*-
"""
Jira Configuration Model
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class JiraConfig(BaseModel):
    """Jira configuration model."""
    server: str = Field(..., description="Jira server URL (e.g., https://yourcompany.atlassian.net)")
    email: str = Field(..., description="Jira user email")
    api_token: str = Field(..., description="Jira API token (will be encrypted)")
    project_keys: List[str] = Field(default=["PRI", "QAB"], description="List of project keys to sync")
    max_issues: int = Field(default=10000, description="Maximum number of issues to fetch")
    date_filter: Optional[str] = Field(default="", description="Date filter (empty for all tickets)")


class JiraConfigUpdate(BaseModel):
    """Jira configuration update model (for API requests)."""
    server: Optional[str] = None
    email: Optional[str] = None
    api_token: Optional[str] = None  # Only provide if changing
    project_keys: Optional[List[str]] = None
    max_issues: Optional[int] = None
    date_filter: Optional[str] = None


class JiraConfigResponse(BaseModel):
    """Jira configuration response model (API response with masked token)."""
    server: str
    email: str
    api_token_masked: str  # Masked token (e.g., "****...1234")
    project_keys: List[str]
    max_issues: int
    date_filter: Optional[str]
    is_configured: bool
    last_test: Optional[str] = None
    test_status: Optional[str] = None
