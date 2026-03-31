from fastapi import APIRouter, Depends

from core.database import db
from core.auth import get_user

router = APIRouter()


@router.get("/correction-memory")
async def list_corrections(user=Depends(get_user)):
    """List all correction memory entries for this restaurant."""
    return await db.correction_memory.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).sort("updated_at", -1).to_list(500)
