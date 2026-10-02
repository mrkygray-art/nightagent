"""Server-side priority rules.

The agent (the LLM) suggests a category and priority, but the business rules live
here in code. The model may escalate a call upward, but it can never downgrade
something policy says is an emergency. That keeps dispatch decisions predictable
and auditable no matter how the conversation goes.
"""

PRIORITY_RANK = {"routine": 0, "urgent": 1, "emergency": 2}

CATEGORY_POLICY = {
    "life_safety": ("emergency", "Fire or life-safety system issue"),
    "cannot_secure_site": ("emergency", "Site cannot be secured (door, gate, or perimeter)"),
    "active_alarm": ("emergency", "Alarm is actively going off"),
    "system_offline": ("urgent", "Security system or video recording is offline"),
    "panel_trouble": ("urgent", "Panel trouble condition"),
    "access_issue": ("routine", "Individual credential or access issue"),
    "other": ("routine", "General service request"),
}

# Common ways the model might phrase a category, mapped to the official one.
_ALIASES = {
    "fire": "life_safety",
    "fire_alarm": "life_safety",
    "door_wont_lock": "cannot_secure_site",
    "door_will_not_lock": "cannot_secure_site",
    "gate_stuck_open": "cannot_secure_site",
    "alarm": "active_alarm",
    "camera_down": "system_offline",
    "cameras_offline": "system_offline",
    "recording_down": "system_offline",
    "beeping": "panel_trouble",
    "trouble": "panel_trouble",
    "badge": "access_issue",
    "credential": "access_issue",
}


def normalize_category(category: str | None) -> str:
    key = (category or "other").strip().lower().replace(" ", "_").replace("-", "_")
    key = _ALIASES.get(key, key)
    return key if key in CATEGORY_POLICY else "other"


def normalize_priority(priority: str | None) -> str:
    key = (priority or "routine").strip().lower()
    return key if key in PRIORITY_RANK else "routine"


def triage(category: str | None, suggested_priority: str | None) -> tuple[str, str, str]:
    """Return (category, final_priority, reason)."""
    category = normalize_category(category)
    policy_priority, reason = CATEGORY_POLICY[category]
    suggested = normalize_priority(suggested_priority)

    if PRIORITY_RANK[suggested] > PRIORITY_RANK[policy_priority]:
        return category, suggested, f"{reason}; escalated based on the caller's description"
    return category, policy_priority, reason
