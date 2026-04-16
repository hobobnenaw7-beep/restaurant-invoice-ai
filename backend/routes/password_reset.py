"""
Password Reset Token Management + Rate Limiting
=================================================
Handles:
- Secure token generation (64-char hex, cryptographically random)
- Token storage in MongoDB with TTL auto-expiry
- One-time-use invalidation
- Rate limiting (max 3 requests per email per hour)
- Manager-only restriction (non-managers get generic response)
- Abstract email layer (log-based for now, swappable to Resend/SendGrid)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import secrets
import logging

from core.database import db
from core.auth import hash_pw, verify_pw

logger = logging.getLogger("restaurant_ai")

router = APIRouter()

TOKEN_EXPIRY_MINUTES = 15
MAX_REQUESTS_PER_HOUR = 3
GENERIC_SUCCESS_MSG = "If the account is eligible, a reset link has been sent."


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ─────────────────────────────────────────────────────────────────────
# Abstract Email Layer
# Swap this function to integrate Resend/SendGrid later.
# ─────────────────────────────────────────────────────────────────────

async def send_reset_email(email: str, reset_url: str):
    """
    Send password reset email.
    Currently: logs to backend console (development mode).
    Future: swap to Resend/SendGrid with zero changes to the security flow.
    """
    logger.info(
        f"PASSWORD RESET LINK (dev mode):\n"
        f"  Email: {email}\n"
        f"  Reset URL: {reset_url}\n"
        f"  Expires: {TOKEN_EXPIRY_MINUTES} minutes"
    )


# ─────────────────────────────────────────────────────────────────────
# Rate Limiting
# ─────────────────────────────────────────────────────────────────────

async def _check_rate_limit(email: str) -> bool:
    """Returns True if the request is within rate limits, False if exceeded."""
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    count = await db.password_reset_tokens.count_documents({
        "email": email.lower().strip(),
        "created_at": {"$gte": one_hour_ago.isoformat()},
    })
    return count < MAX_REQUESTS_PER_HOUR


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """
    Request a password reset link.
    - Always returns generic success message (doesn't reveal if email exists)
    - Only managers get a reset token; other roles are silently skipped
    - Rate limited to 3 requests per email per hour
    """
    email = data.email.lower().strip()

    # Rate limit check (before any DB lookup to prevent enumeration)
    if not await _check_rate_limit(email):
        # Still return generic message — don't reveal rate limiting applies
        return {"message": GENERIC_SUCCESS_MSG}

    # Look up user
    user = await db.users.find_one({"email": email}, {"_id": 0})

    if user and user.get("role") == "manager" and user.get("status") != "inactive":
        # Generate secure token
        token = secrets.token_hex(32)  # 64-char hex string
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

        await db.password_reset_tokens.insert_one({
            "token": token,
            "user_id": user["id"],
            "email": email,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used": False,
        })

        # Build reset URL
        import os
        frontend_url = os.environ.get("FRONTEND_URL", "")
        if not frontend_url:
            backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
            if backend_url:
                frontend_url = backend_url
            else:
                # Read from frontend .env as last resort
                try:
                    with open("/app/frontend/.env") as f:
                        for line in f:
                            if line.startswith("REACT_APP_BACKEND_URL="):
                                frontend_url = line.strip().split("=", 1)[1]
                                break
                except FileNotFoundError:
                    frontend_url = "http://localhost:3000"

        reset_url = f"{frontend_url}/reset-password?token={token}"

        # Send email (log-based for now)
        await send_reset_email(email, reset_url)

        logger.info(f"Password reset token created for {email} (expires {expires_at.isoformat()})")
    else:
        # Non-manager or non-existent email: log silently, return same message
        if user and user.get("role") != "manager":
            logger.info(f"Password reset requested for non-manager role ({user.get('role')}): {email}")
        else:
            logger.info(f"Password reset requested for unknown email: {email}")

    return {"message": GENERIC_SUCCESS_MSG}


@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """
    Reset password using a valid token.
    - Token must exist, not be expired, not be used
    - Password is hashed with same bcrypt as auth system
    - Token is invalidated immediately after successful reset
    """
    if len(data.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    # Find the token
    token_doc = await db.password_reset_tokens.find_one(
        {"token": data.token, "used": False},
        {"_id": 0},
    )

    if not token_doc:
        raise HTTPException(400, "Invalid or expired reset link")

    # Check expiry
    expires_at = datetime.fromisoformat(token_doc["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        # Mark as used so it can't be retried
        await db.password_reset_tokens.update_one(
            {"token": data.token},
            {"$set": {"used": True}},
        )
        raise HTTPException(400, "Reset link has expired. Please request a new one.")

    # Find the user
    user = await db.users.find_one({"id": token_doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(400, "Invalid or expired reset link")

    # Update password
    new_hash = hash_pw(data.new_password)
    await db.users.update_one(
        {"id": token_doc["user_id"]},
        {"$set": {
            "password_hash": new_hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    # Invalidate the token immediately
    await db.password_reset_tokens.update_one(
        {"token": data.token},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}},
    )

    logger.info(f"Password successfully reset for user {token_doc['email']}")

    return {"message": "Password has been reset successfully. You can now sign in."}


@router.get("/auth/verify-reset-token")
async def verify_reset_token(token: str):
    """
    Verify a reset token is valid (for frontend to check before showing form).
    Does NOT consume the token.
    """
    token_doc = await db.password_reset_tokens.find_one(
        {"token": token, "used": False},
        {"_id": 0},
    )

    if not token_doc:
        return {"valid": False, "reason": "invalid"}

    expires_at = datetime.fromisoformat(token_doc["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return {"valid": False, "reason": "expired"}

    return {"valid": True}
