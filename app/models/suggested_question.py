"""
Suggested Questions Model for Dynamic Question Management

This model stores suggested questions that appear on the chat interface.
Questions can be:
- Predefined by admins
- User-submitted and approved
- AI-generated based on popular topics
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


class QuestionStatus(str, Enum):
    """Status of suggested questions"""
    ACTIVE = "active"  # Currently shown to users
    INACTIVE = "inactive"  # Hidden but not deleted
    PENDING = "pending"  # Awaiting admin approval
    REJECTED = "rejected"  # Rejected by admin


class QuestionCategory(str, Enum):
    """Categories for organizing questions"""
    MIGRATION = "migration"
    PRICING = "pricing"
    FEATURES = "features"
    SUPPORT = "support"
    INTEGRATION = "integration"
    SECURITY = "security"
    GENERAL = "general"


class SuggestedQuestion(BaseModel):
    """Model for suggested questions"""
    question_text: str = Field(..., min_length=10, max_length=200, description="The question text")
    category: QuestionCategory = Field(default=QuestionCategory.GENERAL, description="Question category")
    status: QuestionStatus = Field(default=QuestionStatus.ACTIVE, description="Question status")
    
    # Metadata
    priority: int = Field(default=50, ge=0, le=100, description="Display priority (higher = more likely to show)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(None, description="User ID who created this question")
    
    # Analytics
    display_count: int = Field(default=0, description="How many times shown to users")
    click_count: int = Field(default=0, description="How many times clicked")
    click_rate: float = Field(default=0.0, description="Click-through rate (%)")
    
    # Targeting (optional)
    target_user_roles: Optional[List[str]] = Field(None, description="Show only to specific user roles")
    keywords: Optional[List[str]] = Field(None, description="Keywords for context-aware display")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question_text": "How do I migrate data from Slack to Microsoft Teams?",
                "category": "migration",
                "status": "active",
                "priority": 80,
                "keywords": ["slack", "teams", "migration", "chat"],
                "display_count": 1250,
                "click_count": 87,
                "click_rate": 6.96
            }
        }
    )


class QuestionCreate(BaseModel):
    """Schema for creating new questions"""
    question_text: str = Field(..., min_length=10, max_length=200)
    category: QuestionCategory = QuestionCategory.GENERAL
    priority: int = Field(default=50, ge=0, le=100)
    keywords: Optional[List[str]] = None
    target_user_roles: Optional[List[str]] = None


class QuestionUpdate(BaseModel):
    """Schema for updating questions"""
    question_text: Optional[str] = Field(None, min_length=10, max_length=200)
    category: Optional[QuestionCategory] = None
    status: Optional[QuestionStatus] = None
    priority: Optional[int] = Field(None, ge=0, le=100)
    keywords: Optional[List[str]] = None
    target_user_roles: Optional[List[str]] = None


class QuestionAnalyticsUpdate(BaseModel):
    """Schema for updating analytics data"""
    action: str = Field(..., description="Action type: 'display' or 'click'")
    question_id: str = Field(..., description="Question ID")


class QuestionResponse(BaseModel):
    """Response model for questions"""
    id: str
    question_text: str
    category: str
    priority: int
    click_rate: float

