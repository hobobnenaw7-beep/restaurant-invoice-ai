def compute_approval_status(user, amount):
    """Determine approval_status for a new record based on user's approval rule."""
    role = user.get("role", "staff")
    if role == "manager":
        return "approved"
    rule = user.get("approval_rule", "pending_all")
    if rule == "auto_approve_all":
        return "approved"
    if rule == "auto_approve_below":
        limit = user.get("auto_approve_limit")
        if limit is not None and amount <= limit:
            return "approved"
        return "pending"
    return "pending"
