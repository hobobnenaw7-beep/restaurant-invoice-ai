from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import hash_pw, verify_pw, make_token, get_user, require_manager
from core.models import UserRegister, UserLogin, UserCreate, UserUpdate
from services.audit import audit_log

router = APIRouter()

VALID_ROLES = ["manager", "accountant", "cashier", "staff"]

ALL_PERMISSIONS = [
    "can_add_sales", "can_edit_sales", "can_delete_sales",
    "can_add_expenses", "can_edit_expenses", "can_delete_expenses",
    "can_upload_files", "can_view_reports", "can_export_reports",
    "can_view_records", "can_manage_vendors", "can_manage_items",
    "can_manage_users",
]

DEFAULT_PERMISSIONS = {
    "manager": {p: True for p in ALL_PERMISSIONS},
    "accountant": {
        "can_add_sales": True, "can_edit_sales": True, "can_delete_sales": False,
        "can_add_expenses": True, "can_edit_expenses": True, "can_delete_expenses": False,
        "can_upload_files": True, "can_view_reports": True, "can_export_reports": True,
        "can_view_records": True, "can_manage_vendors": True, "can_manage_items": True,
        "can_manage_users": False,
    },
    "cashier": {
        "can_add_sales": True, "can_edit_sales": False, "can_delete_sales": False,
        "can_add_expenses": False, "can_edit_expenses": False, "can_delete_expenses": False,
        "can_upload_files": False, "can_view_reports": False, "can_export_reports": False,
        "can_view_records": False, "can_manage_vendors": False, "can_manage_items": False,
        "can_manage_users": False,
    },
    "staff": {
        "can_add_sales": False, "can_edit_sales": False, "can_delete_sales": False,
        "can_add_expenses": False, "can_edit_expenses": False, "can_delete_expenses": False,
        "can_upload_files": True, "can_view_reports": False, "can_export_reports": False,
        "can_view_records": False, "can_manage_vendors": False, "can_manage_items": False,
        "can_manage_users": False,
    },
}

VALID_APPROVAL_RULES = ["auto_approve_all", "auto_approve_below", "pending_all"]


def _safe_user(u):
    """Return user dict without password_hash, with permissions and approval defaulted."""
    out = {k: v for k, v in u.items() if k != "password_hash"}
    if "permissions" not in out:
        out["permissions"] = DEFAULT_PERMISSIONS.get(out.get("role", "staff"), DEFAULT_PERMISSIONS["staff"])
    if "approval_rule" not in out:
        out["approval_rule"] = "auto_approve_all" if out.get("role") == "manager" else "pending_all"
    if "auto_approve_limit" not in out:
        out["auto_approve_limit"] = None
    return out


# ==================== AUTH ROUTES ====================

@router.post("/auth/register")
async def register(data: UserRegister):
    if await db.users.find_one({"email": data.email}):
        raise HTTPException(400, "Email already registered")
    rid = str(uuid.uuid4())
    await db.restaurants.insert_one({"id": rid, "name": data.restaurant_name, "address": "", "phone": "", "created_at": datetime.now(timezone.utc).isoformat()})
    uid = str(uuid.uuid4())
    await db.users.insert_one({"id": uid, "email": data.email, "password_hash": hash_pw(data.password), "name": data.name, "restaurant_id": rid, "role": "manager", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()})
    return {"token": make_token(uid), "user": {"id": uid, "email": data.email, "name": data.name, "restaurant_id": rid, "restaurant_name": data.restaurant_name, "role": "manager"}}


@router.post("/auth/login")
async def login(data: UserLogin):
    u = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not u or not verify_pw(data.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    if u.get("status") == "inactive":
        raise HTTPException(403, "Account is deactivated. Contact your manager.")
    r = await db.restaurants.find_one({"id": u["restaurant_id"]}, {"_id": 0})
    await audit_log(u, "LOGIN", "User", u["id"], f'{u["name"]} logged in')
    return {"token": make_token(u["id"]), "user": {"id": u["id"], "email": u["email"], "name": u["name"], "restaurant_id": u["restaurant_id"], "restaurant_name": r["name"] if r else "", "role": u.get("role", "staff")}}


@router.get("/auth/me")
async def me(user=Depends(get_user)):
    r = await db.restaurants.find_one({"id": user["restaurant_id"]}, {"_id": 0})
    return {"id": user["id"], "email": user["email"], "name": user["name"], "restaurant_id": user["restaurant_id"], "restaurant_name": r["name"] if r else "", "role": user.get("role", "staff")}


# ==================== USER MANAGEMENT ====================

@router.get("/users")
async def list_users(user=Depends(get_user)):
    require_manager(user)
    rid = user["restaurant_id"]
    users = await db.users.find({"restaurant_id": rid}, {"_id": 0}).to_list(500)
    return [_safe_user(u) for u in users]


@router.post("/users")
async def create_user(data: UserCreate, user=Depends(get_user)):
    require_manager(user)
    rid = user["restaurant_id"]
    if data.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    if await db.users.find_one({"email": data.email}):
        raise HTTPException(400, "Email already in use")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    uid = str(uuid.uuid4())
    if data.permissions:
        perms = {}
        for p in ALL_PERMISSIONS:
            perms[p] = bool(data.permissions.get(p, False))
    else:
        perms = DEFAULT_PERMISSIONS.get(data.role, DEFAULT_PERMISSIONS["staff"])
    doc = {
        "id": uid,
        "email": data.email,
        "password_hash": hash_pw(data.password),
        "name": data.name,
        "restaurant_id": rid,
        "role": data.role,
        "status": "active",
        "permissions": perms,
        "approval_rule": data.approval_rule if data.approval_rule in VALID_APPROVAL_RULES else "pending_all",
        "auto_approve_limit": data.auto_approve_limit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "User", uid, f'{user["name"]} created user {data.name} ({data.role})', new_value={"name": data.name, "email": data.email, "role": data.role})
    return _safe_user(doc)


@router.put("/users/{user_id}")
async def update_user(user_id: str, data: UserUpdate, user=Depends(get_user)):
    require_manager(user)
    rid = user["restaurant_id"]
    target = await db.users.find_one({"id": user_id, "restaurant_id": rid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.email is not None:
        existing = await db.users.find_one({"email": data.email, "id": {"$ne": user_id}})
        if existing:
            raise HTTPException(400, "Email already in use")
        updates["email"] = data.email
    if data.password is not None:
        if len(data.password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        updates["password_hash"] = hash_pw(data.password)
    if data.role is not None:
        if data.role not in VALID_ROLES:
            raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
        if user_id == user["id"] and data.role != "manager":
            raise HTTPException(400, "You cannot change your own role")
        updates["role"] = data.role
    if data.status is not None:
        if data.status not in ("active", "inactive"):
            raise HTTPException(400, "Status must be 'active' or 'inactive'")
        if user_id == user["id"] and data.status == "inactive":
            raise HTTPException(400, "You cannot deactivate yourself")
        updates["status"] = data.status
    if data.permissions is not None:
        clean_perms = {}
        for p in ALL_PERMISSIONS:
            clean_perms[p] = bool(data.permissions.get(p, False))
        updates["permissions"] = clean_perms
    if data.approval_rule is not None:
        if data.approval_rule not in VALID_APPROVAL_RULES:
            raise HTTPException(400, f"Invalid approval_rule. Must be one of: {', '.join(VALID_APPROVAL_RULES)}")
        updates["approval_rule"] = data.approval_rule
    if data.auto_approve_limit is not None:
        updates["auto_approve_limit"] = data.auto_approve_limit
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    old_vals = {k: target.get(k) for k in updates if k != "updated_at" and k != "password_hash"}
    await db.users.update_one({"id": user_id}, {"$set": updates})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    desc = f'{user["name"]} updated user {target.get("name", "")}'
    action = "UPDATE"
    if "role" in updates and updates["role"] != target.get("role"):
        action = "ROLE_CHANGE"
        desc = f'{user["name"]} changed {target["name"]} role from {target.get("role")} to {updates["role"]}'
    new_vals = {k: updates[k] for k in updates if k != "updated_at" and k != "password_hash"}
    await audit_log(user, action, "User", user_id, desc, old_value=old_vals, new_value=new_vals)
    return _safe_user(updated)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user=Depends(get_user)):
    require_manager(user)
    rid = user["restaurant_id"]
    if user_id == user["id"]:
        raise HTTPException(400, "You cannot delete yourself")
    target = await db.users.find_one({"id": user_id, "restaurant_id": rid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    await db.users.delete_one({"id": user_id, "restaurant_id": rid})
    await audit_log(user, "DELETE", "User", user_id, f'{user["name"]} deleted user {target.get("name", "")}', old_value={"name": target.get("name"), "email": target.get("email"), "role": target.get("role")})
    return {"status": "deleted"}


@router.get("/users/permissions/defaults")
async def get_default_permissions(user=Depends(get_user)):
    require_manager(user)
    return DEFAULT_PERMISSIONS


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(user_id: str, permissions: dict, user=Depends(get_user)):
    require_manager(user)
    rid = user["restaurant_id"]
    target = await db.users.find_one({"id": user_id, "restaurant_id": rid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    clean_perms = {}
    for p in ALL_PERMISSIONS:
        clean_perms[p] = bool(permissions.get(p, False))
    old_perms = target.get("permissions", {})
    await db.users.update_one({"id": user_id}, {"$set": {"permissions": clean_perms, "updated_at": datetime.now(timezone.utc).isoformat()}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    await audit_log(user, "ROLE_CHANGE", "User", user_id, f'{user["name"]} updated permissions for {target.get("name", "")}', old_value={"permissions": old_perms}, new_value={"permissions": clean_perms})
    return _safe_user(updated)
