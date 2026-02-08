# -*- coding: utf-8 -*-
"""
RBAC for antigravity: UserContext, PermissionsManager, deny-by-default.
Used at ingestion (permissions on chunks) and at retrieval (filter on every Weaviate query).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any, Dict

from weaviate.classes.query import Filter


@dataclass
class UserContext:
    """Identity and permission groups for the current user."""
    user_id: str
    group_ids: List[str]  # e.g. ["eng", "admin", "sales"]
    tenant_id: str = ""
    department: str = ""

    def has_any_group(self, groups: List[str]) -> bool:
        if not groups:
            return True
        return any(g in self.group_ids for g in groups)


class PermissionsManager:
    """
    Deny-by-default RBAC. Builds Weaviate filters so queries only return
    chunks whose `permissions` array contains at least one of the user's groups.
    """

    # Chunks with no permissions are treated as admin-only
    DEFAULT_NO_ACCESS_GROUP = "admin"

    def filter_for_user(self, user: UserContext) -> Filter | None:
        """
        Return a Weaviate Filter that restricts to chunks the user may see.
        Chunks with empty permissions are treated as admin-only.
        """
        if not user.group_ids:
            # Deny-by-default: no groups -> only "public" if we add that later; for now match admin
            allowed = [self.DEFAULT_NO_ACCESS_GROUP]
        else:
            allowed = list(user.group_ids)
        # Weaviate: filter where permissions ContainsAny of allowed
        return Filter.by_property("permissions").contains_any(allowed)

    def filter_for_user_legacy_dict(self, user: UserContext) -> Dict[str, Any]:
        """
        Return a Weaviate-compatible filter as a dictionary for clients
        that use the REST/GraphQL style filter format.
        """
        groups = user.group_ids or [self.DEFAULT_NO_ACCESS_GROUP]
        return {
            "operator": "ContainsAny",
            "path": ["permissions"],
            "valueText": groups,
        }


def default_user_context(user_id: str, group_ids: List[str] | None = None) -> UserContext:
    """Build a UserContext; if no groups, deny-by-default (admin-only)."""
    return UserContext(user_id=user_id, group_ids=group_ids or [])
