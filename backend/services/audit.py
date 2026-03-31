import uuid
from datetime import datetime, timezone

from core.database import db


async def audit_log(
    user: dict,
    action_type: str,
    entity_type: str,
    entity_id: str,
    description: str,
    old_value: dict = None,
    new_value: dict = None,
):
    """Create an immutable audit log entry."""
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": user["restaurant_id"],
        "user_id": user["id"],
        "user_name": user.get("name", "Unknown"),
        "user_role": user.get("role", "staff"),
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "description": description,
        "old_value": old_value,
        "new_value": new_value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.audit_logs.insert_one(doc)
