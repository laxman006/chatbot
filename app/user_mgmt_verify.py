#!/usr/bin/env python3
"""
Verification for user management (set_user_active, update_user_profile_by_email).
Uses mocks; no real MongoDB. Run from project root: python -m app.user_mgmt_verify
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_set_user_active_returns_none_for_self():
    from app.mongodb_memory import MongoDBMemoryManager
    from unittest.mock import AsyncMock, MagicMock, patch

    memory = MongoDBMemoryManager()
    with patch.object(memory, "connect", AsyncMock()), patch.object(memory, "database", MagicMock()):
        result = await memory.set_user_active("admin@test.com", "admin@test.com", False)
    assert result is None
    print("  OK set_user_active returns None for self")


async def test_set_user_active_uses_update_many():
    from app.mongodb_memory import MongoDBMemoryManager
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_coll = MagicMock()
    mock_coll.update_many = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    mock_coll.update_one = AsyncMock()
    mock_db = MagicMock()
    def _getitem(self, key):
        return mock_coll if key == "user_activity" else MagicMock()
    mock_db.__getitem__ = _getitem

    memory = MongoDBMemoryManager()
    memory.database = mock_db
    with patch.object(memory, "connect", AsyncMock()):
        result = await memory.set_user_active("admin@test.com", "user@test.com", False)

    assert result is True
    assert mock_coll.update_many.called
    assert not mock_coll.update_one.called
    filter_arg = mock_coll.update_many.call_args[0][0]
    assert "$or" in filter_arg
    assert filter_arg.get("is_active") == {"$ne": False}
    print("  OK set_user_active uses update_many with correct filter")


async def test_set_user_active_not_found_returns_false():
    from app.mongodb_memory import MongoDBMemoryManager
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_coll = MagicMock()
    mock_coll.update_many = AsyncMock(return_value=MagicMock(matched_count=0, modified_count=0))
    memory = MongoDBMemoryManager()
    memory.database = MagicMock()
    def _getitem_nf(self, key):
        return mock_coll if key == "user_activity" else MagicMock()
    memory.database.__getitem__ = _getitem_nf

    with patch.object(memory, "connect", AsyncMock()):
        result = await memory.set_user_active("admin@test.com", "nonexistent@test.com", False)
    assert result is False
    print("  OK set_user_active returns False when not found")


async def test_update_user_profile_by_email_uses_update_many():
    from app.mongodb_memory import MongoDBMemoryManager
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_coll = MagicMock()
    mock_coll.update_many = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    mock_coll.update_one = AsyncMock()
    memory = MongoDBMemoryManager()
    memory.database = MagicMock()
    def _getitem_ua(self, key):
        return mock_coll if key == "user_activity" else MagicMock()
    memory.database.__getitem__ = _getitem_ua

    with patch.object(memory, "connect", AsyncMock()), \
         patch("app.teams_repository.get_team_by_name", return_value={"lead_email": "lead@test.com", "lead": "Lead"}):
        result = await memory.update_user_profile_by_email(
            "admin@test.com", "user@test.com", team_name="Engineering", role=None
        )
    assert result is True
    assert mock_coll.update_many.called
    assert not mock_coll.update_one.called
    print("  OK update_user_profile_by_email uses update_many")


async def test_update_user_profile_by_email_empty_email_returns_false():
    from app.mongodb_memory import MongoDBMemoryManager
    from unittest.mock import AsyncMock, patch

    memory = MongoDBMemoryManager()
    with patch.object(memory, "connect", AsyncMock()):
        result = await memory.update_user_profile_by_email("admin@test.com", "", team_name=None, role=None)
    assert result is False
    result2 = await memory.update_user_profile_by_email("admin@test.com", "   ", team_name=None, role=None)
    assert result2 is False
    print("  OK update_user_profile_by_email returns False for empty email")


def run_tests():
    print("Running user management verification...")
    asyncio.run(test_set_user_active_returns_none_for_self())
    asyncio.run(test_set_user_active_uses_update_many())
    asyncio.run(test_set_user_active_not_found_returns_false())
    asyncio.run(test_update_user_profile_by_email_uses_update_many())
    asyncio.run(test_update_user_profile_by_email_empty_email_returns_false())
    print("All checks passed.")


if __name__ == "__main__":
    run_tests()
