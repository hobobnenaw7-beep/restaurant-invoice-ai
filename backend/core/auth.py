from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta
import os

from .database import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("JWT_SECRET", "fallback-secret")
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)


def hash_pw(pw):
    return pwd_context.hash(pw)


def verify_pw(pw, h):
    return pwd_context.verify(pw, h)


def make_token(uid):
    return jwt.encode(
        {"user_id": uid, "exp": datetime.now(timezone.utc) + timedelta(days=7)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


async def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(401, "User not found")
        if user.get("status") == "inactive":
            raise HTTPException(403, "Account is deactivated")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")


def require_manager(user):
    if user.get("role") != "manager":
        raise HTTPException(403, "Manager access required")
