"""Explicit capability manifest: every module remains incapable of system mutations."""

MODULES = [
    {"id": name, "read": True, "system_actions": False, "application_write": write}
    for name, write in (
        ("system", False),
        ("monitoring", False),
        ("services", False),
        ("containers", False),
        ("ai", True),
        ("settings", True),
        ("alerts", False),
        ("diagnostics", True),
        ("audit", False),
    )
]
