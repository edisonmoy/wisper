from datetime import datetime


def format_age(created_at: str) -> str:
    """Return a human-readable age string for a DB timestamp.

    Under 1 hour: relative ("just now", "5m ago").
    Today: absolute time ("2:30 PM").
    Yesterday: "yesterday 2:30 PM".
    Older: short date ("Jan 5").
    """
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ""
    delta = int((datetime.now() - dt).total_seconds())
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%-I:%M %p")
    if (now.date() - dt.date()).days == 1:
        return f"yesterday {dt.strftime('%-I:%M %p')}"
    return dt.strftime("%b %-d")
