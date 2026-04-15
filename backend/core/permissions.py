"""
Permission and Data Scope Enforcement Helpers
==============================================
Provides FastAPI dependencies for:
- Visibility permission checks (page-level access)
- Action permission checks (CRUD operations)
- Data scope filtering (all vs own records)
- Soft-delete query filtering
"""
from fastapi import Depends, HTTPException
from core.auth import get_user
from core.database import db

# ─────────────────────────────────────────────────────────────────────
# Visibility Permissions — controls which pages a user can access
# ─────────────────────────────────────────────────────────────────────
ALL_VISIBILITY = [
    "view_dashboard", "view_sales", "view_expenses", "view_reports",
    "view_records", "view_vendors", "view_items", "view_users",
]

# ─────────────────────────────────────────────────────────────────────
# Action Permissions — controls what operations a user can perform
# ─────────────────────────────────────────────────────────────────────
ALL_ACTIONS = [
    "can_add_sales", "can_edit_sales", "can_delete_sales",
    "can_add_expenses", "can_edit_expenses", "can_delete_expenses",
    "can_upload_files", "can_view_reports", "can_export_reports",
    "can_view_records", "can_manage_vendors", "can_manage_items",
    "can_manage_users",
]

ALL_PERMISSIONS = ALL_VISIBILITY + ALL_ACTIONS

# ─────────────────────────────────────────────────────────────────────
# Default Permission + Scope Matrix (per role)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_VISIBILITY = {
    "manager": {v: True for v in ALL_VISIBILITY},
    "accountant": {
        "view_dashboard": True, "view_sales": True, "view_expenses": True,
        "view_reports": True, "view_records": True, "view_vendors": True,
        "view_items": True, "view_users": False,
    },
    "cashier": {
        "view_dashboard": True, "view_sales": True, "view_expenses": False,
        "view_reports": False, "view_records": True, "view_vendors": True,
        "view_items": True, "view_users": False,
    },
    "staff": {
        "view_dashboard": True, "view_sales": False, "view_expenses": False,
        "view_reports": False, "view_records": True, "view_vendors": False,
        "view_items": False, "view_users": False,
    },
}

DEFAULT_ACTIONS = {
    "manager": {a: True for a in ALL_ACTIONS},
    "accountant": {
        "can_add_sales": True, "can_edit_sales": True, "can_delete_sales": False,
        "can_add_expenses": True, "can_edit_expenses": True, "can_delete_expenses": False,
        "can_upload_files": True, "can_view_reports": True, "can_export_reports": True,
        "can_view_records": True, "can_manage_vendors": True, "can_manage_items": True,
        "can_manage_users": False,
    },
    "cashier": {
        "can_add_sales": True, "can_edit_sales": True, "can_delete_sales": False,
        "can_add_expenses": False, "can_edit_expenses": False, "can_delete_expenses": False,
        "can_upload_files": True, "can_view_reports": False, "can_export_reports": False,
        "can_view_records": True, "can_manage_vendors": False, "can_manage_items": False,
        "can_manage_users": False,
    },
    "staff": {
        "can_add_sales": False, "can_edit_sales": False, "can_delete_sales": False,
        "can_add_expenses": False, "can_edit_expenses": False, "can_delete_expenses": False,
        "can_upload_files": True, "can_view_reports": False, "can_export_reports": False,
        "can_view_records": True, "can_manage_vendors": False, "can_manage_items": False,
        "can_manage_users": False,
    },
}

DEFAULT_DATA_SCOPE = {
    "manager": "all",
    "accountant": "all",
    "cashier": "own",
    "staff": "own",
}


def get_default_permissions(role: str) -> dict:
    """Return the full merged default permissions dict for a role."""
    vis = DEFAULT_VISIBILITY.get(role, DEFAULT_VISIBILITY["staff"])
    act = DEFAULT_ACTIONS.get(role, DEFAULT_ACTIONS["staff"])
    return {**vis, **act}


def get_default_data_scope(role: str) -> str:
    return DEFAULT_DATA_SCOPE.get(role, "own")


# ─────────────────────────────────────────────────────────────────────
# Permission check helpers
# ─────────────────────────────────────────────────────────────────────

def _user_perms(user: dict) -> dict:
    """Get the effective permissions for a user, with role defaults as fallback."""
    stored = user.get("permissions")
    if stored:
        return stored
    return get_default_permissions(user.get("role", "staff"))


def _user_scope(user: dict) -> str:
    """Get the effective data scope for a user."""
    return user.get("data_scope", get_default_data_scope(user.get("role", "staff")))


def require_permission(permission_key: str):
    """FastAPI dependency factory: raises 403 if user lacks the specified permission."""
    async def _check(user=Depends(get_user)):
        perms = _user_perms(user)
        if not perms.get(permission_key, False):
            raise HTTPException(403, f"Permission denied: {permission_key}")
        return user
    return _check


def require_any_permission(*permission_keys: str):
    """FastAPI dependency factory: raises 403 if user lacks ALL of the specified permissions."""
    async def _check(user=Depends(get_user)):
        perms = _user_perms(user)
        if not any(perms.get(k, False) for k in permission_keys):
            raise HTTPException(403, f"Permission denied: requires one of {permission_keys}")
        return user
    return _check


# ─────────────────────────────────────────────────────────────────────
# Data scope query helpers
# ─────────────────────────────────────────────────────────────────────

def apply_scope_filter(query: dict, user: dict, owner_field: str = "created_by_user_id") -> dict:
    """
    Apply data scope filtering to a MongoDB query.
    - scope "all": no additional filter (sees all restaurant records)
    - scope "own": adds filter for records created by this user only

    The owner_field parameter allows customization for collections that
    use a different field name (e.g. legacy data).
    """
    scope = _user_scope(user)
    if scope == "own":
        query[owner_field] = user["id"]
    return query


def apply_soft_delete_filter(query: dict) -> dict:
    """Exclude soft-deleted records from a query."""
    query["status"] = {"$ne": "deleted"}
    return query


def scope_and_active_query(user: dict, base_query: dict = None, owner_field: str = "created_by_user_id") -> dict:
    """Convenience: build a query with restaurant_id + scope + soft-delete filter."""
    q = base_query or {}
    q["restaurant_id"] = user["restaurant_id"]
    apply_scope_filter(q, user, owner_field)
    apply_soft_delete_filter(q)
    return q
