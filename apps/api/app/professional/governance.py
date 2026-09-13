from __future__ import annotations

ROLE_PERMISSIONS = {
    "owner": {"view", "edit", "upload", "approve", "publish", "manage-members", "revoke"},
    "editor": {"view", "edit", "upload", "comment"},
    "reviewer": {"view", "comment", "approve"},
    "viewer": {"view", "comment"},
}

APPROVAL_STAGES = ("content", "design", "final")


def permission_model() -> dict:
    return {
        "version": "project-governance-v1",
        "roles": {role: sorted(actions) for role, actions in ROLE_PERMISSIONS.items()},
        "approvalStages": list(APPROVAL_STAGES),
        "publicationRequires": ["final-approval", "quality-gate", "rendered-snapshot"],
    }


def can(role: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role, set())


def approval_state(records: list[dict]) -> dict:
    latest = {}
    for record in records:
        stage = str(record.get("stage", ""))
        if stage in APPROVAL_STAGES:
            latest.setdefault(stage, record)
    stages = {
        stage: str(latest.get(stage, {}).get("status", "requested")) for stage in APPROVAL_STAGES
    }
    return {
        "version": "approval-state-v1",
        "stages": stages,
        "readyToPublish": stages["final"] == "approved",
    }
