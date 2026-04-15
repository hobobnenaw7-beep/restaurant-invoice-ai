from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import hash_pw, verify_pw, make_token, get_user, require_manager
from core.models import UserRegister, UserLogin, UserCreate, UserUpdate
from core.permissions import (
    ALL_PERMISSIONS, ALL_VISIBILITY, ALL_ACTIONS,
    get_default_permissions, get_default_data_scope,
    DEFAULT_VISIBILITY, DEFAULT_ACTIONS, DEFAULT_DATA_SCOPE,
)
from services.audit import audit_log

router = APIRouter()

VALID_ROLES = ["manager", "accountant", "cashier", "staff"]
VALID_APPROVAL_RULES = ["auto_approve_all", "auto_approve_below", "pending_all"]


def _safe_user(u):
    """Return user dict without password_hash, with permissions/scope/approval defaulted."""
    out = {k: v for k, v in u.items() if k != "password_hash"}
    role = out.get("role", "staff")
    if "permissions" not in out:
        out["permissions"] = get_default_permissions(role)
    else:
        # Backfill any missing visibility keys into existing permissions
        defaults = get_default_permissions(role)
        for k in ALL_PERMISSIONS:
            if k not in out["permissions"]:
                out["permissions"][k] = defaults.get(k, False)
    if "data_scope" not in out:
        out["data_scope"] = get_default_data_scope(role)
    if "approval_rule" not in out:
        out["approval_rule"] = "auto_approve_all" if role == "manager" else "pending_all"
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
    await db.users.insert_one({
        "id": uid, "email": data.email, "password_hash": hash_pw(data.password),
        "name": data.name, "restaurant_id": rid, "role": "manager", "status": "active",
        "permissions": get_default_permissions("manager"),
        "data_scope": "all",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
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
    safe = _safe_user(user)
    return {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "restaurant_id": user["restaurant_id"],
        "restaurant_name": r["name"] if r else "",
        "role": user.get("role", "staff"),
        "permissions": safe["permissions"],
        "data_scope": safe["data_scope"],
    }


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

    # Merge custom permissions with defaults, ensuring all keys exist
    defaults = get_default_permissions(data.role)
    if data.permissions:
        perms = {}
        for p in ALL_PERMISSIONS:
            perms[p] = bool(data.permissions.get(p, defaults.get(p, False)))
    else:
        perms = defaults

    scope = data.data_scope if data.data_scope in ("all", "own") else get_default_data_scope(data.role)

    doc = {
        "id": uid,
        "email": data.email,
        "password_hash": hash_pw(data.password),
        "name": data.name,
        "restaurant_id": rid,
        "role": data.role,
        "status": "active",
        "permissions": perms,
        "data_scope": scope,
        "approval_rule": data.approval_rule if data.approval_rule in VALID_APPROVAL_RULES else "pending_all",
        "auto_approve_limit": data.auto_approve_limit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_user_id": user["id"],
        "created_by_name": user.get("name", ""),
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
    if data.data_scope is not None:
        if data.data_scope in ("all", "own"):
            updates["data_scope"] = data.data_scope
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
async def get_default_permissions_endpoint(user=Depends(get_user)):
    require_manager(user)
    result = {}
    for role in VALID_ROLES:
        result[role] = get_default_permissions(role)
    return result


@router.get("/users/permissions/schema")
async def get_permissions_schema(user=Depends(get_user)):
    """Return the permission keys and data scope options for the UI."""
    require_manager(user)
    return {
        "visibility_keys": ALL_VISIBILITY,
        "action_keys": ALL_ACTIONS,
        "data_scope_options": ["all", "own"],
        "default_scopes": DEFAULT_DATA_SCOPE,
    }


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
    update_set = {"permissions": clean_perms, "updated_at": datetime.now(timezone.utc).isoformat()}
    if "data_scope" in permissions and permissions["data_scope"] in ("all", "own"):
        update_set["data_scope"] = permissions["data_scope"]
    old_perms = target.get("permissions", {})
    await db.users.update_one({"id": user_id}, {"$set": update_set})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    await audit_log(user, "ROLE_CHANGE", "User", user_id, f'{user["name"]} updated permissions for {target.get("name", "")}', old_value={"permissions": old_perms}, new_value={"permissions": clean_perms})
    return _safe_user(updated)
